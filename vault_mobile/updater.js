import * as FileSystem from 'expo-file-system/legacy';
import * as IntentLauncher from 'expo-intent-launcher';
import { Platform } from 'react-native';

const GITHUB_REPO = 'hiteboar/vault_ingestor';
const GITHUB_API_URL = `https://api.github.com/repos/${GITHUB_REPO}/releases/latest`;

/**
 * Compara dos versiones semánticas (v1 y v2).
 * Devuelve:
 *   1 si v1 > v2
 *  -1 si v1 < v2
 *   0 si v1 == v2
 */
export const compareVersions = (v1, v2) => {
  const cleanV1 = (v1 || '').replace(/^v/i, '').trim();
  const cleanV2 = (v2 || '').replace(/^v/i, '').trim();

  const parts1 = cleanV1.split('.').map(p => parseInt(p, 10) || 0);
  const parts2 = cleanV2.split('.').map(p => parseInt(p, 10) || 0);

  const maxLength = Math.max(parts1.length, parts2.length, 3);
  for (let i = 0; i < maxLength; i++) {
    const num1 = parts1[i] || 0;
    const num2 = parts2[i] || 0;
    if (num1 > num2) return 1;
    if (num1 < num2) return -1;
  }
  return 0;
};

/**
 * Consulta la última versión publicada en GitHub Releases.
 * @param {string} currentVersion - Versión actual de la app (ej. "1.0.0")
 */
export const checkForUpdate = async (currentVersion = '1.0.0') => {
  try {
    const response = await fetch(GITHUB_API_URL, {
      headers: {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'VaultMobileApp'
      }
    });

    if (!response.ok) {
      if (response.status === 404) {
        return { hasUpdate: false, error: 'No hay lanzamientos publicados en GitHub todavía.' };
      }
      return { hasUpdate: false, error: `GitHub API error: ${response.status}` };
    }

    const data = await response.json();
    const latestTag = data.tag_name || data.name || '';
    const cleanLatest = latestTag.replace(/^v/i, '');

    // Comprobar si la versión de GitHub es más reciente que la instalada
    const hasNewerVersion = compareVersions(cleanLatest, currentVersion) > 0;

    // Buscar el archivo .apk en los assets del release
    let apkAsset = null;
    if (data.assets && Array.isArray(data.assets)) {
      apkAsset = data.assets.find(asset => 
        asset.name && asset.name.toLowerCase().endsWith('.apk')
      );
    }

    return {
      hasUpdate: hasNewerVersion && !!apkAsset,
      hasNewerVersion,
      hasApkAsset: !!apkAsset,
      latestVersion: latestTag,
      cleanVersion: cleanLatest,
      releaseName: data.name || latestTag,
      releaseNotes: data.body || 'Sin notas de lanzamiento disponibles.',
      publishedAt: data.published_at,
      apkUrl: apkAsset ? apkAsset.browser_download_url : null,
      apkName: apkAsset ? apkAsset.name : 'vault_update.apk',
      apkSize: apkAsset ? apkAsset.size : 0
    };
  } catch (err) {
    console.warn('[Updater] Error comprobando actualizaciones:', err);
    return { hasUpdate: false, error: err.message };
  }
};

let currentDownloadResumable = null;

/**
 * Descarga el archivo APK reportando el progreso en tiempo real.
 * @param {string} apkUrl - URL de descarga del archivo .apk
 * @param {function} onProgress - Callback ({ percent, downloadedBytes, totalBytes })
 * @returns {Promise<string>} Ruta local del archivo descargado
 */
export const downloadApk = async (apkUrl, onProgress) => {
  const targetFile = `${FileSystem.documentDirectory}vault_update.apk`;

  // Limpiar archivo previo si existía
  try {
    const info = await FileSystem.getInfoAsync(targetFile);
    if (info.exists) {
      await FileSystem.deleteAsync(targetFile, { idempotent: true });
    }
  } catch (_) {}

  const callback = (downloadProgress) => {
    const total = downloadProgress.totalBytesExpectedToWrite;
    const written = downloadProgress.totalBytesWritten;
    const progress = total > 0 ? (written / total) : 0;
    const percent = Math.min(100, Math.round(progress * 100));

    if (onProgress) {
      onProgress({
        percent,
        downloadedBytes: written,
        totalBytes: total > 0 ? total : 0,
      });
    }
  };

  currentDownloadResumable = FileSystem.createDownloadResumable(
    apkUrl,
    targetFile,
    {},
    callback
  );

  const result = await currentDownloadResumable.downloadAsync();
  currentDownloadResumable = null;

  if (!result || !result.uri) {
    throw new Error('Fallo en la descarga: No se obtuvo URI local del APK.');
  }

  return result.uri;
};

/**
 * Cancela una descarga activa en curso.
 */
export const cancelDownload = async () => {
  if (currentDownloadResumable) {
    try {
      await currentDownloadResumable.cancelAsync();
    } catch (_) {}
    currentDownloadResumable = null;
  }
};

/**
 * Abre el instalador de paquetes de Android con el APK descargado.
 * @param {string} localFileUri - Ruta local del archivo .apk
 */
export const installApk = async (localFileUri) => {
  if (Platform.OS !== 'android') {
    throw new Error('La instalación automática de APK solo es compatible con Android.');
  }

  // Obtener content:// URI compatible con el FileProvider de Android
  const contentUri = await FileSystem.getContentUriAsync(localFileUri);
  
  await IntentLauncher.startActivityAsync('android.intent.action.VIEW', {
    data: contentUri,
    flags: 1, // FLAG_GRANT_READ_URI_PERMISSION
    type: 'application/vnd.android.package-archive',
  });
};
