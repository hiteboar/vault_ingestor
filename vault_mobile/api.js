import axios from 'axios';
import * as SecureStore from 'expo-secure-store';

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

export const getMediaUrl = async (item) => {
    const { url, token } = await getConnection();
    const encodedPath = item.web_path.split('/').map(segment => encodeURIComponent(segment)).join('/');
    // We add the token as a query parameter because some mobile Image components ignore headers
    return { uri: `${url}/api/media/file/${encodedPath}?token=${token}`, headers: { 'X-Device-Token': token } };
};

export const getThumbUrl = async (item) => {
    const { url, token } = await getConnection();
    return { uri: `${url}/api/media/thumbnail/${item.id}?token=${token}`, headers: { 'X-Device-Token': token } };
};

export const uploadFile = async (uri, name, mimeType, folder) => {
    const { url, token } = await getConnection();
    if (!url) throw new Error('Not connected');

    const formData = new FormData();
    formData.append('file', {
        uri,
        name,
        type: mimeType
    });
    formData.append('context', folder);

    const resp = await fetch(`${url}/api/upload`, {
        method: 'POST',
        headers: {
            'X-Device-Token': token,
            'Content-Type': 'multipart/form-data',
        },
        body: formData,
    });

    if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(txt || 'Upload error');
    }
    return await resp.json();
};

export const verifyPin = async (baseUrl, pin) => {
    console.log(`[DEBUG] verifyPin called with URL: ${baseUrl} and PIN: ${pin}`);
    const url = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
    try {
        const resp = await axios.post(`${url}/api/auth/verify`, { pin }, {
            timeout: 15000,
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                // Fallbacks just in case
                'ngrok-skip-browser-warning': 'true',
                'Bypass-Tunnel-Reminder': 'true'
            }
        });
        console.log(`[DEBUG] verifyPin success! Response:`, resp.data);
        return resp.data.token;
    } catch (error) {
        console.log(`[DEBUG] verifyPin error! Message:`, error.message);
        if (error.response) {
            console.log(`[DEBUG] Response Status:`, error.response.status);
            // Si la respuesta es un HTML (como la advertencia de Cloudflare), esto lo mostrará
            console.log(`[DEBUG] Response Data (first 200 chars):`, typeof error.response.data === 'string' ? error.response.data.substring(0, 200) : error.response.data);
        } else if (error.request) {
            console.log(`[DEBUG] Request sent but no response received.`);
        }
        throw error;
    }
};

export const deleteItem = async (itemId) => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.delete(`/api/items/${itemId}`);
    return resp.data;
};

export const deleteFolder = async (folderName) => {
    const client = await getClient();
    if (!client) throw new Error('Not connected');
    const resp = await client.delete(`/api/folders/${folderName}`);
    return resp.data;
};
