import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import * as FileSystem from 'expo-file-system';
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

export const uploadFile = async (uri, name, mimeType, folder, originalDate, onProgressCallback, onCancelCallback) => {
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
                    onProgressCallback(event.progress);
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
