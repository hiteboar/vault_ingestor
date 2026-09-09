import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import * as FileSystem from 'expo-file-system/legacy';
import { startUpload, onProgress, onCompleted, onError, cancelUpload } from 'rn-background-upload';

const TOKEN_KEY = 'vault_device_token';
const URL_KEY = 'vault_server_url';

export const saveConnection = async (url, token) => {
    await SecureStore.setItemAsync(TOKEN_KEY, token);
    await SecureStore.setItemAsync(URL_KEY, url);
};

export const getConnection = async () => {
    const url = await SecureStore.getItemAsync(URL_KEY);
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    return { url, token };
};

export const clearConnection = async () => {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(URL_KEY);
};

const getClient = async () => {
    const { url, token } = await getConnection();
    if (!url) return null;
    
    return axios.create({
        baseURL: url,
        headers: {
            'X-Device-Token': token
        }
    });
};

export const getMe = async () => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.get('/api/auth/me');
    return resp.data;
};

export const createInvite = async (folders) => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.post('/api/auth/invite', { folders });
    return resp.data;
};

export const fetchStatus = async () => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.get('/api/system/status');
    return resp.data;
};

export const fetchItems = async () => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.get('/api/items');
    return resp.data;
};

export const fetchFoldersMeta = async () => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.get('/api/folders/meta');
    return resp.data;
};

export const fetchItemInfo = async (itemId) => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.get(`/api/items/${itemId}/info`);
    return resp.data;
};

export const getMediaUrl = async (item) => {
    const { url, token } = await getConnection();
    const encodedPath = item.web_path.split('/').map(segment => encodeURIComponent(segment)).join('/');
    return { uri: `${url}/api/media/file/${encodedPath}?token=${token}`, headers: { 'X-Device-Token': token } };
};

export const getThumbUrl = async (item) => {
    const { url, token } = await getConnection();
    return { uri: `${url}/api/media/thumbnail/${item.id}?token=${token}`, headers: { 'X-Device-Token': token } };
};

const CHUNK_SIZE = 5 * 1024 * 1024; // 5 MB per chunk
const CHUNK_THRESHOLD = 5 * 1024 * 1024; // Files >= 5MB use chunked upload
const MAX_CHUNK_RETRIES = 3;

/**
 * Uploads large files in chunks of 5MB with automatic retry, cancellation,
 * and immediate server-side cleanup if connection is lost.
 */
export const uploadFileChunked = async (uri, name, mimeType, folder, originalDate, onProgressCallback, onCancelCallback) => {
    const { url, token } = await getConnection();
    if (!url) throw new Error('Not connected');

    // 1. Determine exact file size
    let totalSize = 0;
    let effectiveUri = uri;
    let createdTempProbe = false;

    try {
        const info = await FileSystem.getInfoAsync(uri);
        if (info.exists && typeof info.size === 'number' && info.size > 0) {
            totalSize = info.size;
        }
    } catch (_) {}

    // For content:// URIs where size may be reported as 0 by ContentResolver, copy temporarily to probe size
    if (totalSize === 0) {
        try {
            const probeUri = `${FileSystem.cacheDirectory}probe_${Date.now()}_${name}`;
            await FileSystem.copyAsync({ from: uri, to: probeUri });
            createdTempProbe = true;
            effectiveUri = probeUri;
            const probeInfo = await FileSystem.getInfoAsync(probeUri);
            totalSize = probeInfo.size || 0;
        } catch (_) {}
    }

    if (totalSize <= 0) {
        if (createdTempProbe) {
            try { await FileSystem.deleteAsync(effectiveUri, { idempotent: true }); } catch (_) {}
        }
        // Fallback to direct upload if size cannot be determined
        return uploadFileDirect(uri, name, mimeType, folder, originalDate, onProgressCallback, onCancelCallback);
    }

    const totalChunks = Math.max(1, Math.ceil(totalSize / CHUNK_SIZE));

    let isCancelled = false;
    let activeUploadId = null;
    let currentTempChunk = null;

    if (onCancelCallback) {
        onCancelCallback(async () => {
            isCancelled = true;
            if (currentTempChunk) {
                try { await FileSystem.deleteAsync(currentTempChunk, { idempotent: true }); } catch (_) {}
            }
            if (createdTempProbe) {
                try { await FileSystem.deleteAsync(effectiveUri, { idempotent: true }); } catch (_) {}
            }
            if (activeUploadId) {
                try {
                    await fetch(`${url}/api/upload/chunk/cancel`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Device-Token': token
                        },
                        body: JSON.stringify({ upload_id: activeUploadId })
                    });
                } catch (_) {}
            }
        });
    }

    try {
        // 2. Initialize chunk session on server
        const initResp = await fetch(`${url}/api/upload/chunk/init`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Device-Token': token
            },
            body: JSON.stringify({
                filename: name,
                total_size: totalSize,
                chunk_size: CHUNK_SIZE,
                total_chunks: totalChunks,
                context: folder,
                original_date: originalDate || null
            })
        });

        if (!initResp.ok) {
            const errBody = await initResp.text();
            throw new Error(`Error al iniciar subida (${initResp.status}): ${errBody}`);
        }

        const initData = await initResp.json();
        const uploadId = initData.upload_id;
        activeUploadId = uploadId;

        // 3. Upload each chunk sequentially with retry policy
        let uploadedBytesSoFar = 0;

        for (let chunkIdx = 0; chunkIdx < totalChunks; chunkIdx++) {
            if (isCancelled) {
                throw new Error('Upload cancelled');
            }

            const offset = chunkIdx * CHUNK_SIZE;
            const currentChunkLength = Math.min(CHUNK_SIZE, totalSize - offset);
            const tempChunkUri = `${FileSystem.cacheDirectory}chunk_${uploadId}_${chunkIdx}.tmp`;
            currentTempChunk = tempChunkUri;

            // Extract binary slice as base64
            const chunkBase64 = await FileSystem.readAsStringAsync(effectiveUri, {
                encoding: FileSystem.EncodingType.Base64,
                position: offset,
                length: currentChunkLength
            });

            // Write slice to temporary cache file
            await FileSystem.writeAsStringAsync(tempChunkUri, chunkBase64, {
                encoding: FileSystem.EncodingType.Base64
            });

            let chunkSuccess = false;
            let lastErr = null;

            for (let attempt = 1; attempt <= MAX_CHUNK_RETRIES; attempt++) {
                if (isCancelled) break;
                try {
                    const uploadRes = await FileSystem.uploadAsync(
                        `${url}/api/upload/chunk`,
                        tempChunkUri,
                        {
                            httpMethod: 'POST',
                            uploadType: FileSystem.FileSystemUploadType.MULTIPART,
                            fieldName: 'chunk',
                            parameters: {
                                upload_id: uploadId,
                                chunk_index: String(chunkIdx)
                            },
                            headers: {
                                'X-Device-Token': token
                            }
                        }
                    );

                    if (uploadRes && uploadRes.status >= 200 && uploadRes.status < 300) {
                        chunkSuccess = true;
                        break;
                    } else {
                        lastErr = new Error(`HTTP ${uploadRes ? uploadRes.status : 'desconocido'}`);
                    }
                } catch (err) {
                    lastErr = err;
                }

                // Wait with backoff before retry (1.5s, 3s, 4.5s)
                if (attempt < MAX_CHUNK_RETRIES && !isCancelled) {
                    await new Promise(r => setTimeout(r, attempt * 1500));
                }
            }

            // Immediately delete local temporary chunk
            try {
                await FileSystem.deleteAsync(tempChunkUri, { idempotent: true });
            } catch (_) {}
            currentTempChunk = null;

            if (isCancelled) {
                throw new Error('Upload cancelled');
            }

            if (!chunkSuccess) {
                // Connection lost indefinitely - notify server to clean up chunks (prevent disk leak)
                try {
                    await fetch(`${url}/api/upload/chunk/cancel`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Device-Token': token
                        },
                        body: JSON.stringify({ upload_id: uploadId })
                    });
                } catch (_) {}

                throw new Error(`Conexión perdida tras ${MAX_CHUNK_RETRIES} intentos. La subida de "${name}" se canceló para liberar espacio (${lastErr ? lastErr.message : 'Timeout'}).`);
            }

            uploadedBytesSoFar += currentChunkLength;
            const percent = Math.min(99, Math.round((uploadedBytesSoFar / totalSize) * 100));

            if (onProgressCallback) {
                onProgressCallback({
                    percent,
                    loadedBytes: uploadedBytesSoFar,
                    totalBytes: totalSize,
                    currentChunk: chunkIdx + 1,
                    totalChunks,
                    status: 'uploading'
                });
            }
        }

        if (isCancelled) {
            throw new Error('Upload cancelled');
        }

        // 4. Notify UI that bytes are 100% uploaded and server is assembling/processing
        if (onProgressCallback) {
            onProgressCallback({
                percent: 100,
                loadedBytes: totalSize,
                totalBytes: totalSize,
                currentChunk: totalChunks,
                totalChunks,
                status: 'processing'
            });
        }

        // 5. Complete assembly on server
        const completeResp = await fetch(`${url}/api/upload/chunk/complete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Device-Token': token
            },
            body: JSON.stringify({ upload_id: uploadId })
        });

        if (!completeResp.ok) {
            const errText = await completeResp.text();
            throw new Error(`Error al ensamblar archivo ${name}: HTTP ${completeResp.status} - ${errText}`);
        }

        return await completeResp.json();
    } finally {
        if (createdTempProbe) {
            try { await FileSystem.deleteAsync(effectiveUri, { idempotent: true }); } catch (_) {}
        }
    }
};

/**
 * Direct multipart upload using rn-background-upload with extended 1-hour timeouts
 * for smaller files (< 5MB).
 */
export const uploadFileDirect = async (uri, name, mimeType, folder, originalDate, onProgressCallback, onCancelCallback) => {
    const { url, token } = await getConnection();
    if (!url) throw new Error('Not connected');

    // rn-background-upload needs an absolute local path, not a file:// URI
    const localPath = uri.startsWith('file://') ? uri.replace('file://', '') : uri;

    // Build query-string style parameters as form fields
    const parameters = { context: folder, filename: name };
    if (originalDate) parameters.original_date = originalDate;

    return new Promise((resolve, reject) => {
        let uploadId = null;
        let progressSub = null;
        let completeSub = null;
        let errorSub = null;

        const cleanup = () => {
            try { progressSub && progressSub.remove(); } catch (_) {}
            try { completeSub && completeSub.remove(); } catch (_) {}
            try { errorSub && errorSub.remove(); } catch (_) {}
        };

        startUpload({
            url: `${url}/api/upload`,
            path: localPath,
            method: 'POST',
            type: 'multipart',
            field: 'file',
            headers: {
                'X-Device-Token': token,
            },
            parameters,
            notification: { enabled: false }, // We use expo-notifications ourselves
            connectTimeout: 60,
            writeTimeout: 3600,
            readTimeout: 3600,
            maxRetries: 3,
        }).then((id) => {
            uploadId = id;

            // Expose a cancel function to the caller
            if (onCancelCallback) {
                onCancelCallback(() => {
                    cancelUpload(uploadId).catch(() => {});
                });
            }

            progressSub = onProgress((event) => {
                if (event.id === uploadId && onProgressCallback) {
                    const loaded = parseInt(event.uploadedBytes, 10) || 0;
                    const total = parseInt(event.totalBytes, 10) || 0;
                    onProgressCallback({
                        percent: event.progress,
                        loadedBytes: loaded,
                        totalBytes: total,
                        status: event.progress >= 100 ? 'processing' : 'uploading'
                    });
                }
            });

            completeSub = onCompleted((event) => {
                if (event.id !== uploadId) return;
                cleanup();
                if (event.responseCode >= 200 && event.responseCode < 300) {
                    try {
                        resolve(JSON.parse(event.responseBody));
                    } catch (_) {
                        resolve({});
                    }
                } else {
                    let errorMsg = 'Upload error';
                    try {
                        const body = JSON.parse(event.responseBody);
                        errorMsg = body.detail || errorMsg;
                    } catch (_) {}
                    reject(new Error(`${errorMsg} (HTTP ${event.responseCode})`));
                }
            });

            errorSub = onError((event) => {
                if (event.id !== uploadId) return;
                cleanup();
                reject(new Error(event.error || 'Upload failed'));
            });

        }).catch((err) => {
            cleanup();
            reject(new Error(err.message || 'Could not start upload'));
        });
    });
};

/**
 * Intelligent file upload router:
 * Automatically uses chunked upload for files >= 5MB (bypassing Cloudflare 100MB body limits and socket timeouts),
 * or direct background upload with 1h timeouts for smaller files.
 */
export const uploadFile = async (uri, name, mimeType, folder, originalDate, onProgressCallback, onCancelCallback) => {
    let fileSize = 0;
    try {
        const info = await FileSystem.getInfoAsync(uri);
        if (info.exists && typeof info.size === 'number' && info.size > 0) {
            fileSize = info.size;
        }
    } catch (_) {}

    // Files >= 5MB use chunked upload. Files < 5MB (or unknown) use chunked if large or direct.
    if (fileSize >= CHUNK_THRESHOLD || fileSize === 0) {
        return uploadFileChunked(uri, name, mimeType, folder, originalDate, onProgressCallback, onCancelCallback);
    } else {
        return uploadFileDirect(uri, name, mimeType, folder, originalDate, onProgressCallback, onCancelCallback);
    }
};


export const verifyPin = async (baseUrl, pin) => {
    const url = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
    const resp = await fetch(`${url}/api/auth/verify`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify({ pin })
    });
    
    if (!resp.ok) {
        throw new Error(`HTTP Error ${resp.status}`);
    }
    
    const data = await resp.json();
    return data.token;
};

export const deleteItem = async (itemId) => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.delete(`/api/items/${itemId}`);
    return resp.data;
};

export const fetchFolders = async () => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.get('/api/folders');
    return resp.data;
};

export const createFolder = async (folderName) => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.post(`/api/folders`, { name: folderName });
    return resp.data;
};

export const deleteFolder = async (folderName) => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.delete(`/api/folders/${folderName}`);
    return resp.data;
};
