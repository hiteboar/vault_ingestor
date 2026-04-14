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
    const { url } = await getConnection();
    return `${url}/api/media/${item.web_path}`;
};

export const getThumbUrl = async (item) => {
    const { url } = await getConnection();
    return `${url}/api/media/thumbnail/${item.id}`;
};

export const verifyPin = async (baseUrl, pin) => {
    // Normalizing URL
    const url = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
    const resp = await axios.post(`${url}/api/auth/verify`, { pin });
    return resp.data.token;
};
