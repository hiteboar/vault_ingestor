import React, { useState, useEffect } from 'react';
import { 
  StyleSheet, 
  Text, 
  View, 
  TouchableOpacity, 
  TextInput, 
  FlatList, 
  Image, 
  ActivityIndicator,
  StatusBar,
  Dimensions,
  Modal,
  Alert,
  PanResponder,
  ScrollView,
  Switch
} from 'react-native';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
import { WebView } from 'react-native-webview';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Video, ResizeMode } from 'expo-av';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import * as MediaLibrary from 'expo-media-library';
import * as api from './api';
import * as updater from './updater';
import { AppState } from 'react-native';
import { useShareIntent } from 'expo-share-intent';
import * as Notifications from 'expo-notifications';

const APP_VERSION = '1.0.3';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

const { width, height } = Dimensions.get('window');
const COLUMN_COUNT = 3;
const ITEM_WIDTH = width / COLUMN_COUNT - 4;

// Utility to format sizes
const formatBytes = (bytes, decimals = 2) => {
  if (!bytes || bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
};

function MainApp() {
  const insets = useSafeAreaInsets();
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('gallery'); // 'gallery', 'stats', or 'map'
  const [compressedMode, setCompressedMode] = useState(true);
  
  // Linking state
  const [url, setUrl] = useState('');
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  
  // Scanner state
  const [permission, requestPermission] = useCameraPermissions();
  const [showScanner, setShowScanner] = useState(false);
  const [scanned, setScanned] = useState(false);

  // Data & Role state
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState(null);
  const [role, setRole] = useState('standard');
  const [currentFolder, setCurrentFolder] = useState('root');
  const [foldersMeta, setFoldersMeta] = useState({});
  const [sortMode, setSortMode] = useState('time');
  const [showSortMenu, setShowSortMenu] = useState(false);
  
  // Modals state
  const initialUploadState = {
    active: false,
    current: 0,
    total: 0,
    currentFileName: '',
    filePercent: 0,
    fileLoadedBytes: 0,
    fileTotalBytes: 0,
    overallPercent: 0,
    totalLoadedBytes: 0,
    totalBatchBytes: 0,
    statusText: ''
  };
  const [uploadMenuVisible, setUploadMenuVisible] = useState(false);
  const [uploadState, setUploadState] = useState(initialUploadState);
  const [isCancellingUpload, setIsCancellingUpload] = useState(false);
  const activeUploadCancelRef = React.useRef(null); // holds { cancel: fn } for current upload
  
  // Custom Gallery state
  const [galleryVisible, setGalleryVisible] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [galleryAssets, setGalleryAssets] = useState([]);
  const [selectedGalleryIds, setSelectedGalleryIds] = useState(new Set());
  const [galleryHasNextPage, setGalleryHasNextPage] = useState(true);
  const [galleryEndCursor, setGalleryEndCursor] = useState(null);
  const [galleryLoading, setGalleryLoading] = useState(false);
  const [previewItem, setPreviewItem] = useState(null);
  const [previewSrc, setPreviewSrc] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const [showInfo, setShowInfo] = useState(false);
  const [fileInfo, setFileInfo] = useState(null);
  const [infoLoading, setInfoLoading] = useState(false);
  const [inviteModal, setInviteModal] = useState(false);
  const [inviteData, setInviteData] = useState(null);
  const [newFolderModal, setNewFolderModal] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  
  // Share Intent state
  const { hasShareIntent, shareIntent, resetShareIntent } = useShareIntent();
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareFiles, setShareFiles] = useState([]);
  const [shareUploadState, setShareUploadState] = useState(initialUploadState);
  const activeShareUploadCancelRef = React.useRef(null);
  const [selectedShareFolder, setSelectedShareFolder] = useState('root');
  
  // Date filters for timeline
  const [selectedYear, setSelectedYear] = useState('All');
  const [selectedMonth, setSelectedMonth] = useState('All');
  
  // UI - Drawer & Refresh
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [inviteConfigModal, setInviteConfigModal] = useState(false);
  const [selectedInviteFolders, setSelectedInviteFolders] = useState(['root']);
  const [lastUpdated, setLastUpdated] = useState(new Date());

  // App Update state
  const [updateInfo, setUpdateInfo] = useState(null);
  const [updateModalVisible, setUpdateModalVisible] = useState(false);
  const [isCheckingUpdate, setIsCheckingUpdate] = useState(false);
  const [isInstalling, setIsInstalling] = useState(false);
  const [updateDownloadState, setUpdateDownloadState] = useState({
    downloading: false,
    percent: 0,
    downloadedBytes: 0,
    totalBytes: 0,
    error: null,
    downloadedUri: null,
  });

  const handleCheckUpdate = async (manual = false) => {
    if (isCheckingUpdate) return;
    setIsCheckingUpdate(true);
    try {
      const result = await updater.checkForUpdate(APP_VERSION);
      if (result.hasUpdate) {
        setUpdateInfo(result);
        setUpdateModalVisible(true);
      } else if (manual) {
        if (result.error) {
          Alert.alert('Actualizaciones', result.error);
        } else if (result.hasNewerVersion && !result.hasApkAsset) {
          Alert.alert(
            'Nueva versión detectada',
            `Se ha publicado la versión ${result.latestVersion}, pero aún no tiene el archivo APK adjunto en GitHub Releases.`
          );
        } else {
          Alert.alert(
            'Actualizaciones',
            `¡Estás al día! Vault Mobile v${APP_VERSION} es la versión más reciente.`
          );
        }
      }
    } catch (e) {
      if (manual) Alert.alert('Error', 'No se pudo comprobar la actualización: ' + e.message);
    } finally {
      setIsCheckingUpdate(false);
    }
  };

  const handleInstallUpdate = async (uriToInstall) => {
    const targetUri = uriToInstall || updateDownloadState.downloadedUri;
    if (!targetUri) {
      Alert.alert('Error', 'No se ha encontrado el archivo descargado. Vuelve a descargarlo.');
      return;
    }

    setIsInstalling(true);
    try {
      await updater.installApk(targetUri);
    } catch (err) {
      console.error('Error al intentar instalar actualización:', err);
      Alert.alert(
        'Instalación de actualización',
        `No se pudo abrir el instalador automáticamente (${err.message || 'Fallo desconocido'}).\n\nSi es la primera vez, asegúrate de activar "Instalar aplicaciones desconocidas" para Vault Mobile en los Ajustes del sistema.`,
        [
          { text: 'Cancelar', style: 'cancel' },
          {
            text: 'Abrir Ajustes',
            onPress: () => updater.openInstallPermissionSettings(),
          },
          {
            text: 'Abrir con otra app',
            onPress: () => updater.shareApk(targetUri),
          },
        ]
      );
    } finally {
      setIsInstalling(false);
    }
  };

  const handleStartDownloadUpdate = async () => {
    if (!updateInfo || !updateInfo.apkUrl) {
      Alert.alert('Error', 'No hay enlace de descarga disponible para el APK.');
      return;
    }

    setUpdateDownloadState({
      downloading: true,
      percent: 0,
      downloadedBytes: 0,
      totalBytes: updateInfo.apkSize || 0,
      error: null,
      downloadedUri: null,
    });

    try {
      const localUri = await updater.downloadApk(updateInfo.apkUrl, (progress) => {
        setUpdateDownloadState(prev => ({
          ...prev,
          percent: progress.percent,
          downloadedBytes: progress.downloadedBytes,
          totalBytes: progress.totalBytes || prev.totalBytes,
        }));
      });

      setUpdateDownloadState(prev => ({
        ...prev,
        downloading: false,
        downloadedUri: localUri,
      }));

      // Trigger installer automatically
      await handleInstallUpdate(localUri);
    } catch (err) {
      console.error('Error downloading/installing update:', err);
      setUpdateDownloadState(prev => ({
        ...prev,
        downloading: false,
        error: err.message,
      }));
      Alert.alert('Fallo en la actualización', 'No se pudo completar la instalación: ' + err.message);
    }
  };

  const handleCancelUpdateDownload = async () => {
    await updater.cancelDownload();
    setUpdateDownloadState({
      downloading: false,
      percent: 0,
      downloadedBytes: 0,
      totalBytes: 0,
      error: null,
      downloadedUri: null,
    });
    setUpdateModalVisible(false);
  };

  useEffect(() => {
    checkConnection();
    // Silent update check in background 3s after startup
    const updateTimer = setTimeout(() => {
      handleCheckUpdate(false);
    }, 3000);
    return () => clearTimeout(updateTimer);
  }, []);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', nextAppState => {
      if (nextAppState === 'active') {
        loadData();
      }
    });

    // Refresh interval: 30s general, 1s in stats
    const interval = setInterval(() => {
        loadData(false); // Silent load
    }, view === 'stats' ? 1000 : 30000);

    return () => {
      subscription.remove();
      clearInterval(interval);
    };
  }, [connected, view]);

  useEffect(() => {
    if (hasShareIntent && shareIntent && shareIntent.files && shareIntent.files.length > 0) {
      if (!connected) {
        Alert.alert(
          'Not Connected',
          'Please link this device to your Vault Storage system first in order to share files.',
          [{ text: 'OK', onPress: () => resetShareIntent() }]
        );
        return;
      }
      setSelectedShareFolder(currentFolder === 'root' ? 'root' : currentFolder);
      const filesWithDates = shareIntent.files.map(file => ({
          ...file,
          customDate: file.contentDate || ''
      }));
      setShareFiles(filesWithDates);
      setShowShareModal(true);
    }
  }, [hasShareIntent, shareIntent, connected]);

  const checkConnection = async () => {
    const conn = await api.getConnection();
    if (conn.token && conn.url) {
      setConnected(true);
      await loadData();
    } else {
        setLoading(false);
    }
  };

  const loadData = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const me = await api.getMe();
      setRole(me.role);
      if (me.role !== 'admin' && me.allowed_folders.length > 0 && currentFolder === 'root') {
          setCurrentFolder(me.allowed_folders[0]);
      }

      const [itemsList, sysStatus, fMeta] = await Promise.all([
        api.fetchItems(),
        api.fetchStatus(),
        api.fetchFoldersMeta().catch(() => ({}))
      ]);
      
      const uniqueMap = new Map();
      itemsList.forEach(item => {
        uniqueMap.set(item.id, item);
      });
      
      setItems(Array.from(uniqueMap.values()));
      setStatus(sysStatus);
      setFoldersMeta(fMeta || {});
      setLastUpdated(new Date());
      setError('');
    } catch (e) {
      if (e.response?.status === 401) {
        handleLogout();
      } else {
        setError('Conexión perdida con el servidor.');
        setConnected(false);
      }
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  const handleLink = async () => {
    setError('');
    setLoading(true);
    try {
      const token = await api.verifyPin(url, pin);
      await api.saveConnection(url, token);
      setConnected(true);
      await loadData();
    } catch (e) {
      setError('Link error. Check URL and PIN or permissions.');
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    await api.clearConnection();
    setUrl('');
    setPin('');
    setConnected(false);
  };

  const openScanner = async () => {
    if (!permission?.granted) {
      const result = await requestPermission();
      if (!result.granted) {
         setError('Camera permission is required for scanning.');
         return;
      }
    }
    setScanned(false);
    setShowScanner(true);
  };

  const handleDeleteItem = async () => {
    if (!previewItem) return;
    
    Alert.alert(
        'Delete File',
        'Are you sure you want to delete this file permanently?',
        [
            { text: 'Cancel', style: 'cancel' },
            { 
                text: 'Delete', 
                style: 'destructive',
                onPress: async () => {
                    try {
                        setLoading(true);
                        await api.deleteItem(previewItem.id);
                        setPreviewItem(null);
                        await loadData();
                    } catch (e) {
                        alert('Delete error: ' + e.message);
                    } finally {
                        setLoading(false);
                    }
                }
            }
        ]
    );
  };

  const handleBulkDelete = async () => {
    if (selectedItems.size === 0) return;
    
    Alert.alert(
        'Eliminar Archivos',
        `¿Seguro que deseas eliminar ${selectedItems.size} archivos permanentemente?`,
        [
            { text: 'Cancelar', style: 'cancel' },
            { 
                text: 'Eliminar', 
                style: 'destructive',
                onPress: async () => {
                    try {
                        setLoading(true);
                        const ids = Array.from(selectedItems);
                        for (let i = 0; i < ids.length; i++) {
                            await api.deleteItem(ids[i]);
                        }
                        setSelectedItems(new Set());
                        setSelectionMode(false);
                        await loadData();
                    } catch (e) {
                        alert('Error al eliminar: ' + e.message);
                    } finally {
                        setLoading(false);
                    }
                }
            }
        ]
    );
  };

  const handleBulkDownload = async () => {
    if (selectedItems.size === 0) return;
    const { status } = await MediaLibrary.requestPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permiso denegado', 'Se necesita acceso a tus fotos para poder descargar.');
      return;
    }

    try {
        setLoading(true);
        const ids = Array.from(selectedItems);
        let downloadedCount = 0;
        for (let i = 0; i < ids.length; i++) {
            const item = items.find(it => it.id === ids[i]);
            if (item) {
                const src = await api.getMediaUrl(item);
                const ext = item.name.split('.').pop().toLowerCase();
                const isMedia = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'mov', 'm4v', 'avi', 'mkv', 'webm'].includes(ext);
                if (isMedia) {
                    const fileUri = FileSystem.cacheDirectory + item.name;
                    const downloadRes = await FileSystem.downloadAsync(src.uri, fileUri, { headers: src.headers });
                    await MediaLibrary.saveToLibraryAsync(downloadRes.uri);
                    downloadedCount++;
                }
            }
        }
        setSelectedItems(new Set());
        setSelectionMode(false);
        Alert.alert('Descarga Completa', `Se guardaron ${downloadedCount} archivos en tu galería.`);
    } catch (e) {
        alert('Error al descargar: ' + e.message);
    } finally {
        setLoading(false);
    }
  };

  const handleDeleteFolder = async () => {
      if (currentFolder === 'root') return;
      
      Alert.alert(
          'Delete Folder',
          `Are you sure you want to delete folder "${currentFolder}" and ALL its physical files?`,
          [
              { text: 'Cancel', style: 'cancel' },
              { 
                  text: 'Delete All', 
                  style: 'destructive',
                  onPress: async () => {
                        try {
                            setLoading(true);
                            await api.deleteFolder(currentFolder);
                            setCurrentFolder('root');
                            await loadData();
                        } catch (e) {
                            alert('Error deleting folder: ' + e.message);
                        } finally {
                            setLoading(false);
                        }
                  }
              }
          ]
      );
  };

  const handleCreateFolder = async () => {
      if (!newFolderName.trim()) return;
      try {
          setLoading(true);
          await api.createFolder(newFolderName.trim());
          setCurrentFolder(newFolderName.trim());
          setNewFolderName('');
          setNewFolderModal(false);
          await loadData();
      } catch (e) {
          alert('Error creating folder: ' + e.message);
      } finally {
          setLoading(false);
      }
  };
  const handleBarcodeScanned = ({ type, data }) => {
    setScanned(true);
    setShowScanner(false);
    try {
      const payload = JSON.parse(data);
      if (payload.url && payload.pin) {
        setUrl(payload.url);
        setPin(payload.pin);
        setError('');
      } else {
        setError('QR inválido (Faltan datos).');
      }
    } catch (e) {
        setError('El código QR no es válido para Vault.');
    }
  };

  const processUploads = async (assets) => {
      setUploadMenuVisible(false);
      if (!assets || assets.length === 0) return;

      const { status: existingStatus } = await Notifications.getPermissionsAsync();
      let finalStatus = existingStatus;
      if (existingStatus !== 'granted') {
          const { status } = await Notifications.requestPermissionsAsync();
          finalStatus = status;
      }

      // Pre-calculate total queue size in bytes
      let totalBatchBytes = 0;
      const assetSizes = [];
      for (let i = 0; i < assets.length; i++) {
          let size = assets[i].size || 0;
          if (!size && assets[i].uri) {
              try {
                  const info = await FileSystem.getInfoAsync(assets[i].uri);
                  if (info.exists && typeof info.size === 'number' && info.size > 0) {
                      size = info.size;
                  }
              } catch (_) {}
          }
          assetSizes.push(size);
          totalBatchBytes += size;
      }

      setUploadState({
          active: true,
          current: 0,
          total: assets.length,
          currentFileName: '',
          filePercent: 0,
          fileLoadedBytes: 0,
          fileTotalBytes: 0,
          overallPercent: 0,
          totalLoadedBytes: 0,
          totalBatchBytes: totalBatchBytes,
          statusText: 'Preparando subida...'
      });
      setIsCancellingUpload(false);
      let successCount = 0;
      let anyFallback = false;
      let cancelled = false;
      let previousCompletedBytes = 0;
      const totalFiles = assets.length;
      
      if (finalStatus === 'granted') {
          await Notifications.scheduleNotificationAsync({
              identifier: "upload-queue",
              content: { title: "Subiendo archivos...", body: `(0 / ${totalFiles}) - Vault Ingestor` },
              trigger: null,
          });
      }
      
      for (let i = 0; i < assets.length; i++) {
          const asset = assets[i];
          const mimeType = asset.mimeType || asset.type || 'application/octet-stream';
          let filename = asset.name || asset.fileName || asset.uri.split('/').pop() || 'upload.bin';
          const currentFileExpectedSize = assetSizes[i] || 0;
          
          // Ensure filename has a valid extension if we know the mimeType
          if (!filename.includes('.') || filename.endsWith('.tmp') || filename.endsWith('.bin')) {
              const extMap = {
                  'image/jpeg': '.jpg',
                  'image/jpg': '.jpg',
                  'image/png': '.png',
                  'image/webp': '.webp',
                  'image/heic': '.heic',
                  'image/heif': '.heif',
                  'video/mp4': '.mp4',
                  'video/quicktime': '.mov',
                  'video/x-matroska': '.mkv',
                  'application/pdf': '.pdf'
              };
              let ext = extMap[mimeType.toLowerCase()];
              if (!ext) {
                  if (mimeType.toLowerCase().startsWith('image/')) {
                      ext = '.jpg';
                  } else if (mimeType.toLowerCase().startsWith('video/')) {
                      ext = '.mp4';
                  }
              }
              if (ext) {
                  const base = filename.replace(/\.(tmp|bin)$/i, '');
                  filename = base + ext;
              }
          }

          setUploadState(prev => ({
              ...prev,
              current: i + 1,
              currentFileName: filename,
              filePercent: 0,
              fileLoadedBytes: 0,
              fileTotalBytes: currentFileExpectedSize,
              statusText: 'Iniciando subida...'
          }));
          
          // Check for cancellation before each file
          if (cancelled) break;

          try {
              let originalDate = null;
              if (asset.exif && asset.exif.DateTimeOriginal) {
                  const parts = asset.exif.DateTimeOriginal.split(' ');
                  if (parts.length === 2) {
                      originalDate = `${parts[0].replace(/:/g, '-')}T${parts[1]}Z`;
                  }
              }
              if (!originalDate && asset.creationTime) {
                  originalDate = new Date(asset.creationTime * (asset.creationTime > 1e11 ? 1 : 1000)).toISOString();
              }
                  
              const resp = await api.uploadFile(
                  asset.uri, 
                  filename, 
                  mimeType, 
                  currentFolder, 
                  originalDate, 
                  (prog) => {
                      let filePct = 0;
                      let fileLoaded = 0;
                      let fileTot = currentFileExpectedSize;
                      let statusText = 'Subiendo...';

                      if (typeof prog === 'number') {
                          filePct = prog;
                          fileLoaded = Math.round((prog / 100) * (fileTot || 1));
                      } else if (prog && typeof prog === 'object') {
                          filePct = prog.percent || 0;
                          fileLoaded = prog.loadedBytes || 0;
                          fileTot = prog.totalBytes || fileTot;
                          if (prog.status === 'processing') {
                              statusText = 'Procesando en servidor...';
                          } else if (prog.currentChunk && prog.totalChunks) {
                              statusText = `Subiendo parte ${prog.currentChunk} de ${prog.totalChunks}...`;
                          }
                      }

                      const totalLoaded = previousCompletedBytes + fileLoaded;
                      const overallPercent = totalBatchBytes > 0 
                          ? Math.min(100, Math.round((totalLoaded / totalBatchBytes) * 100))
                          : filePct;

                      setUploadState(prev => ({
                          ...prev,
                          filePercent: filePct,
                          fileLoadedBytes: fileLoaded,
                          fileTotalBytes: fileTot,
                          totalLoadedBytes: totalLoaded,
                          overallPercent,
                          statusText
                      }));
                  }, 
                  (cancelFn) => { activeUploadCancelRef.current = cancelFn; }
              );
              activeUploadCancelRef.current = null;
              if (resp && resp.fallback_used) anyFallback = true;
              successCount++;
              previousCompletedBytes += currentFileExpectedSize;
              
              if (finalStatus === 'granted' && (successCount % Math.max(1, Math.floor(totalFiles/10)) === 0 || successCount === totalFiles)) {
                  await Notifications.scheduleNotificationAsync({
                      identifier: "upload-queue",
                      content: {
                          title: successCount === totalFiles ? "¡Subida completada!" : "Subiendo archivos...",
                          body: successCount === totalFiles ? `Se han subido ${successCount} archivos.` : `(${successCount} / ${totalFiles}) - Vault Ingestor`
                      },
                      trigger: null,
                  });
              }
          } catch(e) {
              activeUploadCancelRef.current = null;
              if (e.message && e.message.includes('cancel')) {
                  cancelled = true;
              } else if (e.message && e.message.includes('Conexión perdida')) {
                  Alert.alert("Error de conexión", e.message);
                  cancelled = true; // Stop remaining queue when connection is permanently lost
              } else {
                  Alert.alert("Error de subida", `Error al subir ${filename}: ${e.message}`);
              }
          }
      }
      
      activeUploadCancelRef.current = null;
      setIsCancellingUpload(false);
      setUploadState(initialUploadState);
      loadData();
      if (successCount > 0 && successCount < assets.length) {
          if (anyFallback) {
              Alert.alert("Carga parcial con advertencias", `Se subieron ${successCount} de ${assets.length} archivos, pero algunos se registraron con la fecha actual.`);
          } else {
              Alert.alert("Carga parcial", `Se subieron ${successCount} de ${assets.length} archivos correctamente.`);
          }
      } else if (successCount === assets.length && anyFallback) {
          Alert.alert("Carga con advertencias", "Todos los archivos se subieron, pero algunos no contenían fecha original y se registraron con la actual.");
      }
  };

  const handleShareUpload = async () => {
      if (!shareFiles || shareFiles.length === 0) return;
      
      const assets = shareFiles;
      const { status: existingStatus } = await Notifications.getPermissionsAsync();
      let finalStatus = existingStatus;
      if (existingStatus !== 'granted') {
          const { status } = await Notifications.requestPermissionsAsync();
          finalStatus = status;
      }

      // Pre-calculate file sizes to provide accurate byte progress across the queue
      const assetSizes = [];
      let totalBatchBytes = 0;
      for (const asset of assets) {
          let size = asset.fileSize || asset.size || 0;
          if (!size && asset.path) {
              try {
                  const safePath = asset.path.startsWith('file://') ? asset.path : `file://${asset.path}`;
                  const info = await FileSystem.getInfoAsync(safePath);
                  if (info.exists && info.size) size = info.size;
              } catch (err) {
                  // ignore
              }
          }
          assetSizes.push(size);
          totalBatchBytes += size;
      }

      setShareUploadState({
          active: true,
          current: 0,
          total: assets.length,
          currentFileName: '',
          filePercent: 0,
          fileLoadedBytes: 0,
          fileTotalBytes: 0,
          overallPercent: 0,
          totalLoadedBytes: 0,
          totalBatchBytes,
          statusText: 'Iniciando subida...'
      });

      let successCount = 0;
      let anyFallback = false;
      const totalFiles = assets.length;
      let previousCompletedBytes = 0;
      let cancelled = false;
      
      if (finalStatus === 'granted') {
          await Notifications.scheduleNotificationAsync({
              identifier: "upload-queue",
              content: { title: "Subiendo compartidos...", body: `(0 / ${totalFiles}) - Vault Ingestor` },
              trigger: null,
          });
      }
      
      for (let i = 0; i < assets.length; i++) {
          const asset = assets[i];
          const currentFileExpectedSize = assetSizes[i] || 0;
          const mimeType = asset.mimeType || asset.type || 'application/octet-stream';
          let filename = asset.fileName || (asset.path ? asset.path.split('/').pop() : null) || `shared_${Date.now()}.bin`;
          
          // Ensure filename has a valid extension if we know the mimeType
          if (!filename.includes('.') || filename.endsWith('.tmp') || filename.endsWith('.bin')) {
              const extMap = {
                  'image/jpeg': '.jpg',
                  'image/jpg': '.jpg',
                  'image/png': '.png',
                  'image/webp': '.webp',
                  'image/heic': '.heic',
                  'image/heif': '.heif',
                  'video/mp4': '.mp4',
                  'video/quicktime': '.mov',
                  'video/x-matroska': '.mkv',
                  'application/pdf': '.pdf'
              };
              let ext = extMap[mimeType.toLowerCase()];
              if (!ext) {
                  if (mimeType.toLowerCase().startsWith('image/')) {
                      ext = '.jpg';
                  } else if (mimeType.toLowerCase().startsWith('video/')) {
                      ext = '.mp4';
                  }
              }
              if (ext) {
                  const base = filename.replace(/\.(tmp|bin)$/i, '');
                  filename = base + ext;
              }
          }

          setShareUploadState(prev => ({
              ...prev,
              current: i + 1,
              currentFileName: filename,
              filePercent: 0,
              fileLoadedBytes: 0,
              fileTotalBytes: currentFileExpectedSize,
              statusText: 'Iniciando subida...'
          }));

          if (cancelled) break;

          try {
              let originalDate = asset.customDate || null;
              
              // Upload the cached file — binary content is identical to original, EXIF is preserved in the bytes
              const safePath = asset.path || '';
              const fileUriToUpload = safePath.startsWith('file://') ? safePath : `file://${safePath}`;

              const resp = await api.uploadFile(
                  fileUriToUpload, 
                  filename, 
                  mimeType, 
                  selectedShareFolder, 
                  originalDate, 
                  (prog) => {
                      let filePct = 0;
                      let fileLoaded = 0;
                      let fileTot = currentFileExpectedSize;
                      let statusText = 'Subiendo...';

                      if (typeof prog === 'number') {
                          filePct = prog;
                          fileLoaded = Math.round((prog / 100) * (fileTot || 1));
                      } else if (prog && typeof prog === 'object') {
                          filePct = prog.percent || 0;
                          fileLoaded = prog.loadedBytes || 0;
                          fileTot = prog.totalBytes || fileTot;
                          if (prog.status === 'processing') {
                              statusText = 'Procesando en servidor...';
                          } else if (prog.currentChunk && prog.totalChunks) {
                              statusText = `Subiendo parte ${prog.currentChunk} de ${prog.totalChunks}...`;
                          }
                      }

                      const totalLoaded = previousCompletedBytes + fileLoaded;
                      const overallPercent = totalBatchBytes > 0 
                          ? Math.min(100, Math.round((totalLoaded / totalBatchBytes) * 100))
                          : filePct;

                      setShareUploadState(prev => ({
                          ...prev,
                          filePercent: filePct,
                          fileLoadedBytes: fileLoaded,
                          fileTotalBytes: fileTot,
                          totalLoadedBytes: totalLoaded,
                          overallPercent,
                          statusText
                      }));
                  },
                  (cancelFn) => { activeShareUploadCancelRef.current = cancelFn; }
              );
              activeShareUploadCancelRef.current = null;
              if (resp && resp.fallback_used) anyFallback = true;
              successCount++;
              previousCompletedBytes += currentFileExpectedSize;
              
              if (finalStatus === 'granted' && (successCount % Math.max(1, Math.floor(totalFiles/10)) === 0 || successCount === totalFiles)) {
                  await Notifications.scheduleNotificationAsync({
                      identifier: "upload-queue",
                      content: {
                          title: successCount === totalFiles ? "¡Subida completada!" : "Subiendo compartidos...",
                          body: successCount === totalFiles ? `Se han subido ${successCount} archivos.` : `(${successCount} / ${totalFiles}) - Vault Ingestor`
                      },
                      trigger: null,
                  });
              }
          } catch(e) {
              activeShareUploadCancelRef.current = null;
              if (e.message && e.message.includes('cancel')) {
                  cancelled = true;
              } else if (e.message && e.message.includes('Conexión perdida')) {
                  Alert.alert("Error de conexión", e.message);
                  cancelled = true;
              } else {
                  Alert.alert("Error de subida", `Error al subir ${filename}: ${e.message}`);
              }
          }
      }

      activeShareUploadCancelRef.current = null;
      setShareUploadState(initialUploadState);
      setShowShareModal(false);
      resetShareIntent();
      loadData();
      
      if (successCount === assets.length) {
          if (anyFallback) {
              Alert.alert("Carga completada con advertencias", "Todos los archivos se subieron correctamente, pero algunos no contenían fecha original y se registraron con la actual.");
          } else {
              Alert.alert("Subida completada", "Todos los archivos compartidos se subieron correctamente.");
          }
      } else if (successCount > 0) {
          if (anyFallback) {
              Alert.alert("Carga parcial con advertencias", `Se subieron ${successCount} de ${assets.length} archivos, pero algunos se registraron con la fecha actual.`);
          } else {
              Alert.alert("Subida parcial", `Se subieron ${successCount} de ${assets.length} archivos correctamente.`);
          }
      }
  };

  const handlePickDocument = async () => {
    const result = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, multiple: true });
    if (!result.canceled && result.assets && result.assets.length > 0) {
      processUploads(result.assets);
    }
  };

  const loadGallery = async (loadMore = false) => {
    if (galleryLoading) return;
    if (loadMore && !galleryHasNextPage) return;

    setGalleryLoading(true);
    try {
      const options = {
        mediaType: [MediaLibrary.MediaType.photo, MediaLibrary.MediaType.video],
        first: 40,
        sortBy: [MediaLibrary.SortBy.creationTime],
      };
      if (loadMore && galleryEndCursor) {
        options.after = galleryEndCursor;
      }
      const result = await MediaLibrary.getAssetsAsync(options);
      
      setGalleryAssets(prev => loadMore ? [...prev, ...result.assets] : result.assets);
      setGalleryHasNextPage(result.hasNextPage);
      setGalleryEndCursor(result.endCursor);
    } catch (e) {
      console.log('Error loading gallery', e);
      Alert.alert('Error', 'No se pudieron cargar las fotos.');
    } finally {
      setGalleryLoading(false);
    }
  };

  const handlePickMedia = async () => {
    setUploadMenuVisible(false);
    const { status } = await MediaLibrary.requestPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permiso denegado', 'Se necesita acceso a tus fotos para poder subirlas.');
      return;
    }
    setGalleryAssets([]);
    setSelectedGalleryIds(new Set());
    setGalleryHasNextPage(true);
    setGalleryEndCursor(null);
    setGalleryVisible(true);
    loadGallery(false);
  };

  const handleConfirmGallerySelection = async () => {
    if (selectedGalleryIds.size === 0) {
      setGalleryVisible(false);
      return;
    }
    setGalleryVisible(false);
    
    // We need to fetch full info for each selected asset to get localUri/uri
    const assetsToUpload = [];
    for (const id of selectedGalleryIds) {
      const asset = galleryAssets.find(a => a.id === id);
      if (asset) {
        try {
          const assetInfo = await MediaLibrary.getAssetInfoAsync(asset);
          assetsToUpload.push({
            uri: assetInfo.localUri || assetInfo.uri,
            mimeType: assetInfo.mediaType === 'video' ? 'video/mp4' : 'image/jpeg',
            fileName: assetInfo.filename,
            width: assetInfo.width,
            height: assetInfo.height,
            duration: assetInfo.duration
          });
        } catch (e) {
          console.log('Error getting asset info', e);
        }
      }
    }
    
    if (assetsToUpload.length > 0) {
      processUploads(assetsToUpload);
    }
  };

  const toggleGalleryAsset = (id) => {
    setSelectedGalleryIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  const openPreview = async (item) => {
    setPreviewItem(item);
    setPreviewSrc(null);
    setPreviewLoading(true);
    setPreviewError(null);
    setShowInfo(false);
    try {
        const src = await api.getMediaUrl(item);
        setPreviewSrc(src);
    } catch (e) {
        setPreviewError("Could not get file URL");
    }
  };

  const handleDownload = async () => {
    if(!previewItem || !previewSrc) return;
    try {
        const fileUri = FileSystem.cacheDirectory + previewItem.name;
        const downloadRes = await FileSystem.downloadAsync(previewSrc.uri, fileUri, { headers: previewSrc.headers });
        await Sharing.shareAsync(downloadRes.uri);
    } catch (e) {
        alert('Download error: ' + e.message);
    }
  };

  const handleNext = () => {
      if (!previewItem) return;
      const flat = getProcessedItems().flatMap(r => r.type === 'row' ? r.items : []).filter(i => !i.isFolder);
      const idx = flat.findIndex(i => i.id === previewItem.id);
      if (idx !== -1 && idx < flat.length - 1) {
          openPreview(flat[idx + 1]);
      }
  };

  const handlePrev = () => {
      if (!previewItem) return;
      const flat = getProcessedItems().flatMap(r => r.type === 'row' ? r.items : []).filter(i => !i.isFolder);
      const idx = flat.findIndex(i => i.id === previewItem.id);
      if (idx > 0) {
          openPreview(flat[idx - 1]);
      }
  };

  const loadFileInfo = async () => {
      setShowInfo(true);
      setInfoLoading(true);
      try {
          const info = await api.fetchItemInfo(previewItem.id);
          setFileInfo(info);
      } catch (e) {
          alert('Error getting info: ' + e.message);
      } finally {
          setInfoLoading(false);
      }
  };

  const panResponder = React.useRef(
      PanResponder.create({
          onStartShouldSetPanResponder: () => false,
          onMoveShouldSetPanResponder: (evt, gestureState) => {
              return Math.abs(gestureState.dx) > 20;
          },
          onPanResponderRelease: (evt, gestureState) => {
              if (gestureState.dx > 50) {
                  handlePrev();
              } else if (gestureState.dx < -50) {
                  handleNext();
              }
          }
      })
  ).current;

  const handleCreateInvite = async () => {
      try {
          setLoading(true);
          const data = await api.createInvite(selectedInviteFolders);
          setInviteData(data);
          setInviteModal(true);
          setInviteConfigModal(false);
          setDrawerOpen(false);
      } catch (e) {
          alert('Error creating invitation: ' + e.message);
      } finally {
          setLoading(false);
      }
  };

  const toggleInviteFolder = (folder) => {
      if (selectedInviteFolders.includes(folder)) {
          setSelectedInviteFolders(selectedInviteFolders.filter(f => f !== folder));
      } else {
          setSelectedInviteFolders([...selectedInviteFolders, folder]);
      }
  };

  const renderRow = ({ item: row }) => {
      if (row.type === 'type_marker') {
          return (
              <View style={styles.typeMarkerContainer}>
                  <Text style={styles.typeMarkerText}>{row.label}</Text>
                  <View style={styles.typeMarkerLine} />
              </View>
          );
      }
      
      const isTimeline = currentFolder === 'root';
      const availableWidth = isTimeline ? width - 4 - 60 : width - 4;
      const rowItemWidth = Math.floor(availableWidth / COLUMN_COUNT) - 4;
      
      return (
          <View style={[styles.rowContainer, isTimeline && { marginLeft: 10 }, { height: rowItemWidth + 4 }]}>
              {isTimeline && (
                  <View style={styles.sideMarkerContainer}>
                      {row.sideMarker ? (
                          <View style={styles.sideMarkerContent}>
                              <View style={styles.sideMarkerDot} />
                              <Text style={styles.sideMarkerText}>{row.sideMarker}</Text>
                              <View style={styles.sideMarkerLine} />
                          </View>
                      ) : (
                          <View style={styles.sideMarkerLine} />
                      )}
                  </View>
              )}
              <View style={styles.rowItemsContainer}>
                  {row.items.map((item, index) => {
                      if (item.isFolder) {
                          const folderItems = items.filter(i => i.context === item.name).sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || '')).slice(0, 4);
                          return (
                              <TouchableOpacity 
                                  key={item.id} 
                                  style={[styles.folderCard, { width: rowItemWidth, height: rowItemWidth, padding: 0, overflow: 'hidden' }]}
                                  onPress={() => setCurrentFolder(item.name)}
                              >
                                  {folderItems.length > 0 ? (
                                      <View style={{ flex: 1, flexDirection: 'row', flexWrap: 'wrap' }}>
                                          {[...Array(4)].map((_, i) => {
                                              const fi = folderItems[i];
                                              return (
                                                  <View key={i} style={{ width: '50%', height: '50%', padding: 1, backgroundColor: '#1e293b' }}>
                                                      {fi ? <Thumbnail item={fi} customWidth="100%" onPress={() => setCurrentFolder(item.name)} /> : null}
                                                  </View>
                                              );
                                          })}
                                      </View>
                                  ) : (
                                      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
                                          <MaterialCommunityIcons name="folder-multiple" size={32} color="#3b82f6" />
                                      </View>
                                  )}
                                  <View style={{ position: 'absolute', bottom: 0, width: '100%', backgroundColor: 'rgba(15, 23, 42, 0.8)', paddingVertical: 2, alignItems: 'center' }}>
                                      <Text style={[styles.folderCardTitle, { marginTop: 0 }]} numberOfLines={1}>{item.name}</Text>
                                      <Text style={styles.folderCardSub}>
                                          {item.date_range?.newest ? item.date_range.newest.split('T')[0] : ''}
                                      </Text>
                                  </View>
                              </TouchableOpacity>
                          );
                      } else {
                          const isSelected = selectedItems.has(item.id);
                          return (
                              <Thumbnail 
                                  key={item.id}
                                  item={item} 
                                  onPress={() => {
                                      if (selectionMode) {
                                          const newSet = new Set(selectedItems);
                                          if (newSet.has(item.id)) newSet.delete(item.id);
                                          else newSet.add(item.id);
                                          setSelectedItems(newSet);
                                          if (newSet.size === 0) setSelectionMode(false);
                                      } else {
                                          openPreview(item);
                                      }
                                  }} 
                                  onLongPress={() => {
                                      if (!selectionMode) {
                                          setSelectionMode(true);
                                          const newSet = new Set();
                                          newSet.add(item.id);
                                          setSelectedItems(newSet);
                                      }
                                  }}
                                  customWidth={rowItemWidth}
                                  showContextTag={!compressedMode && item.context !== 'root'}
                                  selectionMode={selectionMode}
                                  isSelected={isSelected}
                              />
                          );
                      }
                  })}
              </View>
          </View>
      );
  };

  const getProcessedItems = () => {
      let filtered = items.filter(i => {
          if (currentFolder === 'root') {
              if (compressedMode) {
                  if (i.context !== 'root') return false;
              }
              if (selectedYear !== 'All') {
                  if (!i.timestamp.startsWith(selectedYear)) return false;
              }
              return true;
          }
          return i.context === currentFolder;
      });

      if (currentFolder === 'root' && compressedMode) {
          Object.keys(foldersMeta).forEach(fName => {
              const meta = foldersMeta[fName];
              if (meta && meta.date_range && meta.date_range.newest) {
                  if (selectedYear === 'All' || meta.date_range.newest.startsWith(selectedYear)) {
                      filtered.push({
                          id: `folder-${fName}`,
                          isFolder: true,
                          name: fName,
                          timestamp: meta.date_range.newest,
                          date_range: meta.date_range
                      });
                  }
              }
          });
      }

      if (sortMode === 'time' || currentFolder === 'root') {
          filtered.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));
      } else if (sortMode === 'type') {
          filtered.sort((a, b) => {
              const extA = (a.name || '').split('.').pop().toLowerCase();
              const extB = (b.name || '').split('.').pop().toLowerCase();
              return extA.localeCompare(extB);
          });
      }
      
      let rows = [];
      let currentGroup = null;
      let currentRow = [];
      let pendingMarker = null;

      filtered.forEach((item) => {
          let itemGroup = null;
          
          if (currentFolder === 'root') {
             const dateStr = item.timestamp || '';
             itemGroup = dateStr.substring(0, 7); 
          } else if (sortMode === 'type') {
             itemGroup = (item.name || '').split('.').pop().toLowerCase() || 'otros';
          }

          if (itemGroup !== null && itemGroup !== currentGroup) {
              if (currentRow.length > 0) {
                  rows.push({ type: 'row', id: `row-${rows.length}`, items: currentRow, sideMarker: pendingMarker });
                  currentRow = [];
                  pendingMarker = null;
              }
              
              if (currentFolder === 'root') {
                  const [y, m] = itemGroup.split('-');
                  const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
                  pendingMarker = `${monthNames[parseInt(m, 10)-1] || ''}\n${y}`;
              } else {
                  rows.push({ type: 'type_marker', id: `marker-${rows.length}`, label: itemGroup.toUpperCase() });
              }
              currentGroup = itemGroup;
          }

          currentRow.push(item);
          if (currentRow.length === COLUMN_COUNT) {
              rows.push({ type: 'row', id: `row-${rows.length}`, items: currentRow, sideMarker: pendingMarker });
              currentRow = [];
              pendingMarker = null;
          }
      });
      
      if (currentRow.length > 0) {
          rows.push({ type: 'row', id: `row-${rows.length}`, items: currentRow, sideMarker: pendingMarker });
      }

      return rows;
  };

  if (loading && !connected) {
    return (
      <View style={[styles.container, { paddingTop: insets.top, paddingBottom: insets.bottom, justifyContent: 'center', alignItems: 'center' }]}>
        <StatusBar barStyle="light-content" translucent backgroundColor="transparent" />
        <ActivityIndicator size="large" color="#3b82f6" />
      </View>
    );
  }

  if (!connected) {
      // (Scan & Login UI... omitted largely unchanged but simplified for space)
      if (showScanner) {
        return (
          <View style={[styles.container, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
            <StatusBar barStyle="light-content" translucent backgroundColor="transparent" />
            <CameraView 
              style={StyleSheet.absoluteFillObject}
              facing="back"
              onBarcodeScanned={scanned ? undefined : handleBarcodeScanned}
              barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
            />
            <View style={styles.scannerOverlay}>
               <View style={styles.scannerBox} />
               <TouchableOpacity style={[styles.buttonCancelScanner, { bottom: Math.max(insets.bottom, 20) + 20 }]} onPress={() => setShowScanner(false)}>
                 <Text style={styles.buttonText}>Cancel Scan</Text>
               </TouchableOpacity>
            </View>
          </View>
        );
      }
  
      return (
        <View style={[styles.container, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
          <StatusBar barStyle="light-content" translucent backgroundColor="transparent" />
          <View style={styles.content}>
            <Text style={styles.title}>Link Vault</Text>
            <Text style={styles.subtitle}>Scan a QR to enter.</Text>
            
            <TouchableOpacity style={styles.buttonScan} onPress={openScanner}>
              <Text style={styles.buttonText}>📷 Scan QR Code</Text>
            </TouchableOpacity>
  
            <View style={styles.divider}><Text style={styles.dividerText}>OR MANUALLY</Text></View>
  
            <TextInput style={styles.input} placeholder="Server URL" placeholderTextColor="#64748b" value={url} onChangeText={setUrl} autoCapitalize="none"/>
            <TextInput style={styles.inputPin} placeholder="PIN" placeholderTextColor="#3b82f6" value={pin} onChangeText={setPin} keyboardType="numeric" maxLength={6}/>
            
            {error ? <Text style={styles.errorText}>{error}</Text> : null}
  
            <TouchableOpacity style={[styles.button, (!url || !pin) && styles.buttonDisabled]} onPress={handleLink} disabled={!url || !pin}>
              <Text style={styles.buttonText}>Link</Text>
            </TouchableOpacity>
          </View>
        </View>
      );
  }

  return (
    <View style={[styles.container, { paddingBottom: insets.bottom }]}>
      <StatusBar barStyle="light-content" translucent backgroundColor="transparent" />       
      {/* Header */}
      {selectionMode ? (
        <View style={[styles.header, { backgroundColor: '#1e293b', paddingTop: Math.max(insets.top, 16) + 10 }]}>
            <View style={{flexDirection: 'row', alignItems: 'center'}}>
                <TouchableOpacity onPress={() => { setSelectionMode(false); setSelectedItems(new Set()); }} style={{marginRight:15}}>
                    <MaterialCommunityIcons name="close" size={28} color="#94a3b8" />
                </TouchableOpacity>
                <Text style={styles.headerTitle}>{selectedItems.size} seleccionados</Text>
            </View>
            <View style={{flexDirection: 'row', alignItems:'center'}}>
                <TouchableOpacity onPress={handleBulkDownload} style={{marginRight: 20}}>
                    <MaterialCommunityIcons name="download" size={28} color="#3b82f6" />
                </TouchableOpacity>
                <TouchableOpacity onPress={handleBulkDelete}>
                    <MaterialCommunityIcons name="trash-can-outline" size={28} color="#ef4444" />
                </TouchableOpacity>
            </View>
        </View>
      ) : (
        <View style={[styles.header, { paddingTop: Math.max(insets.top, 16) + 10 }]}>
            <View style={{flexDirection: 'row', alignItems: 'center'}}>
                {view !== 'gallery' && (
                    <TouchableOpacity onPress={() => setView('gallery')} style={{marginRight:15}}>
                        <MaterialCommunityIcons name="arrow-left" size={28} color="#3b82f6" />
                    </TouchableOpacity>
                )}
                <Text style={styles.headerTitle}>{view === 'stats' ? 'Control Panel' : view === 'map' ? 'Map Explorer' : 'Vault Ingestor'}</Text>
            </View>
            <View style={{flexDirection: 'row', alignItems:'center'}}>
                <TouchableOpacity onPress={() => loadData(true)} disabled={loading} style={{marginRight: 20}}>
                    {loading ? <ActivityIndicator size="small" color="#3b82f6"/> : <MaterialCommunityIcons name="refresh" size={28} color="#3b82f6" />}
                </TouchableOpacity>
                {!previewItem && (
                    <TouchableOpacity onPress={() => setDrawerOpen(true)}>
                        <MaterialCommunityIcons name="menu" size={32} color="#fff" />
                    </TouchableOpacity>
                )}
            </View>
        </View>
      )}

      {/* Folder Selector & Management */}
      {view === 'gallery' && (
        <View style={styles.folderSelectorContainer}>
            <View style={styles.folderSelector}>
                <FlatList 
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    style={{ flex: 1 }}
                    data={['root', ...new Set(items.map(i => {
                        // Named folders are those where context isn't 'root'
                        return i.context && i.context !== 'root' ? i.context : null;
                    }).filter(f => f !== null))]}
                    keyExtractor={(f) => f}
                    renderItem={({ item: f }) => (
                        <TouchableOpacity 
                            style={[styles.folderChip, currentFolder === f && styles.folderChipActive]}
                            onPress={() => setCurrentFolder(f)}
                        >
                            <MaterialCommunityIcons 
                                name={f === 'root' ? 'calendar-clock' : 'folder-outline'} 
                                size={16} 
                                color={currentFolder === f ? '#fff' : '#94a3b8'} 
                                style={{marginRight: 6}}
                            />
                            <Text style={[styles.folderChipText, currentFolder === f && styles.folderChipTextActive]}>
                                {f === 'root' ? 'Timeline' : f}
                            </Text>
                        </TouchableOpacity>
                    )}
                />
                <TouchableOpacity style={styles.addFolderBtn} onPress={() => setNewFolderModal(true)}>
                    <MaterialCommunityIcons name="plus" size={24} color="#fff" />
                </TouchableOpacity>
            </View>

            {/* Timeline Filters (Year/Month) */}
            {currentFolder === 'root' && (
                <View style={[styles.filterBar, { justifyContent: 'space-between' }]}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
                        <Text style={styles.filterLabel}>Filter:</Text>
                        <FlatList 
                            horizontal
                            showsHorizontalScrollIndicator={false}
                            data={['All', ...new Set(items.filter(i => compressedMode ? i.context === 'root' : true).map(i => (i.timestamp || '').split('-')[0]).filter(y => y))]}
                            keyExtractor={y => y}
                            renderItem={({item: y}) => (
                               <TouchableOpacity onPress={() => setSelectedYear(y)} style={selectedYear === y ? styles.filterOptActive : styles.filterOpt}>
                                   <Text style={selectedYear === y ? styles.filterOptTextActive : styles.filterOptText}>{y}</Text>
                               </TouchableOpacity>
                            )}
                        />
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', marginLeft: 10 }}>
                        <Text style={styles.filterLabel}>Comprimir</Text>
                        <Switch
                            trackColor={{ false: "#334155", true: "#3b82f6" }}
                            thumbColor={"#f8fafc"}
                            onValueChange={setCompressedMode}
                            value={compressedMode}
                        />
                    </View>
                </View>
            )}

            {/* Folder Actions (Delete & Sort) */}
            {currentFolder !== 'root' && (
                <View style={styles.folderActions}>
                    <View style={{flexDirection: 'row', alignItems: 'center', zIndex: 50}}>
                        <Text style={styles.folderPathText}>Managing: {currentFolder}</Text>
                        <TouchableOpacity style={styles.sortMenuBtn} onPress={() => setShowSortMenu(!showSortMenu)}>
                            <MaterialCommunityIcons name="sort" size={16} color="#94a3b8" />
                            <Text style={styles.sortMenuBtnText}> Sort</Text>
                        </TouchableOpacity>
                        
                        {showSortMenu && (
                            <View style={styles.sortMenuDropdown}>
                                <TouchableOpacity style={styles.sortMenuItem} onPress={() => { setSortMode('time'); setShowSortMenu(false); }}>
                                    <MaterialCommunityIcons name={sortMode === 'time' ? 'check' : 'blank'} size={16} color="#3b82f6" style={{marginRight: 5}}/>
                                    <Text style={[styles.sortMenuItemText, sortMode === 'time' && {color: '#3b82f6'}]}>By time</Text>
                                </TouchableOpacity>
                                <TouchableOpacity style={styles.sortMenuItem} onPress={() => { setSortMode('type'); setShowSortMenu(false); }}>
                                    <MaterialCommunityIcons name={sortMode === 'type' ? 'check' : 'blank'} size={16} color="#3b82f6" style={{marginRight: 5}}/>
                                    <Text style={[styles.sortMenuItemText, sortMode === 'type' && {color: '#3b82f6'}]}>By type</Text>
                                </TouchableOpacity>
                            </View>
                        )}
                    </View>
                    
                    {role === 'admin' && (
                        <TouchableOpacity onPress={handleDeleteFolder} style={styles.deleteFolderBtn}>
                            <MaterialCommunityIcons name="trash-can-outline" size={18} color="#ef4444" />
                            <Text style={styles.deleteFolderText}> Delete Folder</Text>
                        </TouchableOpacity>
                    )}
                </View>
            )}
        </View>
      )}


      {/* Main View */}
      {view === 'gallery' ? (
        <View style={{ flex: 1 }}>

            <FlatList 
            data={getProcessedItems()}
            numColumns={1}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.gallery}
            renderItem={renderRow}
            ListEmptyComponent={<Text style={{color:'#64748b', textAlign:'center', marginTop: 50}}>No files in this folder</Text>}
            // OPTIMIZACIONES DE RENDIMIENTO
            windowSize={7} // Renders 3 screens above/below viewport
            maxToRenderPerBatch={10} // Controls how many items are rendered per batch
            updateCellsBatchingPeriod={50} // Time between batches in ms
            initialNumToRender={12} // Renders 4 rows immediately at start
            removeClippedSubviews={true} // Improves memory on Android by hiding off-screen views
            />

            {/* Static bottom progress bar */}
            {uploadState.active && (
                <View style={{ position: 'absolute', bottom: Math.max(insets.bottom, 15) + 85, left: 15, right: 15, backgroundColor: '#1e293b', padding: 14, borderRadius: 12, borderWidth: 1, borderColor: '#334155', elevation: 8, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.35, shadowRadius: 4, zIndex: 100 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <Text style={{ color: '#fff', fontSize: 13, fontWeight: 'bold', flex: 1, marginRight: 8 }} numberOfLines={1} ellipsizeMode="middle">
                            {isCancellingUpload ? 'Cancelando...' : `(${uploadState.current}/${uploadState.total}) ${uploadState.currentFileName || 'Archivo'}`}
                        </Text>
                        <TouchableOpacity
                            onPress={() => {
                                Alert.alert(
                                    'Cancelar subida',
                                    '¿Seguro que quieres cancelar la subida de archivos pendientes?',
                                    [
                                        { text: 'No', style: 'cancel' },
                                        { text: 'Sí, cancelar', style: 'destructive', onPress: () => {
                                            setIsCancellingUpload(true);
                                            if (activeUploadCancelRef.current) {
                                                activeUploadCancelRef.current();
                                            }
                                        }}
                                    ]
                                );
                            }}
                            style={{ backgroundColor: '#ef4444', borderRadius: 6, paddingHorizontal: 10, paddingVertical: 4 }}
                        >
                            <Text style={{ color: '#fff', fontSize: 11, fontWeight: 'bold' }}>✕ Cancelar</Text>
                        </TouchableOpacity>
                    </View>
                    
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <Text style={{ color: '#94a3b8', fontSize: 11 }}>{uploadState.statusText || 'Subiendo...'}</Text>
                        <Text style={{ color: '#3b82f6', fontSize: 13, fontWeight: 'bold' }}>
                            {uploadState.overallPercent || uploadState.filePercent || 0}%
                        </Text>
                    </View>
                    
                    <View style={{ height: 6, backgroundColor: '#334155', borderRadius: 3, overflow: 'hidden' }}>
                        <View style={{ width: `${Math.min(100, Math.max(0, uploadState.overallPercent || uploadState.filePercent || 0))}%`, height: '100%', backgroundColor: isCancellingUpload ? '#ef4444' : '#3b82f6' }} />
                    </View>

                    <Text style={{ color: '#94a3b8', fontSize: 11, marginTop: 6 }}>
                        {formatBytes(uploadState.fileLoadedBytes)} de {formatBytes(uploadState.fileTotalBytes)} ({uploadState.filePercent}%)
                        {uploadState.total > 1 && uploadState.totalBatchBytes > 0 ? ` • Total: ${formatBytes(uploadState.totalLoadedBytes)} de ${formatBytes(uploadState.totalBatchBytes)}` : ''}
                    </Text>
                </View>
            )}

            {/* Subida Flotante */}
            <View style={[styles.fabContainer, { bottom: Math.max(insets.bottom, 15) + 25 }]}>
                {uploadMenuVisible && (
                    <View style={styles.uploadMenu}>
                        <TouchableOpacity style={styles.uploadMenuItem} onPress={handlePickDocument}>
                            <MaterialCommunityIcons name="file-outline" size={20} color="#fff" />
                            <Text style={styles.uploadMenuText}>Files</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.uploadMenuItem} onPress={handlePickMedia}>
                            <MaterialCommunityIcons name="image-outline" size={20} color="#fff" />
                            <Text style={styles.uploadMenuText}>Images / Videos</Text>
                        </TouchableOpacity>
                    </View>
                )}
                
                {uploadState.active ? (
                    <View style={styles.fab}><ActivityIndicator color="#fff"/></View>
                ) : (
                    <TouchableOpacity 
                        style={[styles.fab, uploadMenuVisible && { backgroundColor: '#ef4444', transform: [{ rotate: '45deg' }] }]} 
                        onPress={() => setUploadMenuVisible(!uploadMenuVisible)}
                    >
                        <MaterialCommunityIcons name="plus" size={32} color="#fff" />
                    </TouchableOpacity>
                )}
            </View>
        </View>
      ) : view === 'map' ? (
        <View style={{ flex: 1, backgroundColor: '#0f172a' }}>
            <WebView
                originWhitelist={['*']}
                source={{ html: getMapHtml() }}
                style={{ flex: 1, backgroundColor: 'transparent' }}
                injectedJavaScript={`window.mapData = ${JSON.stringify(items.filter(i => i.gps))}; initMap();`}
                javaScriptEnabled={true}
                onMessage={(event) => {
                    const data = JSON.parse(event.nativeEvent.data);
                    if (data.action === 'openPreview' && data.id) {
                        const itemToPreview = items.find(i => i.id === data.id);
                        if (itemToPreview) openPreview(itemToPreview);
                    }
                }}
            />
        </View>
      ) : (
        <View style={styles.statsContainer}>
          <View style={styles.statCard}>
             <View style={{flexDirection:'row', alignItems:'center', marginBottom: 10}}>
                <MaterialCommunityIcons name="harddisk" size={20} color="#94a3b8" style={{marginRight:8}} />
                <Text style={styles.statLabel}>Disk Usage</Text>
             </View>
             <View style={styles.progressBarBg}>
                <View style={[styles.progressBarFill, { width: `${status?.disk?.percent || 0}%`, backgroundColor: (status?.disk?.percent > 90 ? '#ef4444' : '#3b82f6') }]} />
             </View>
             <Text style={styles.statValue}>{Math.round(status?.disk?.percent || 0)}%</Text>
             <Text style={styles.statSub}>
                {formatBytes(status?.disk?.used || 0)} utilizados de {formatBytes(status?.disk?.total || 1)}
             </Text>
          </View>

          <View style={styles.statCard}>
             <View style={{flexDirection:'row', alignItems:'center', marginBottom: 10}}>
                <MaterialCommunityIcons name="memory" size={24} color="#94a3b8" style={{marginRight:8}} />
                <Text style={styles.statLabel}>RAM Usage</Text>
             </View>
             <View style={styles.progressBarBg}>
                <View style={[styles.progressBarFill, { width: `${status?.ram?.percent || 0}%`, backgroundColor: (status?.ram?.percent > 85 ? '#f59e0b' : '#10b981') }]} />
             </View>
             <Text style={styles.statValue}>{Math.round(status?.ram?.percent || 0)}%</Text>
             <Text style={styles.statSub}>
                {formatBytes(status?.ram?.used || 0)} / {formatBytes(status?.ram?.total || 1)}
             </Text>
          </View>

          <View style={styles.statCard}>
             <View style={{flexDirection:'row', alignItems:'center', marginBottom: 10}}>
                <MaterialCommunityIcons name="folder-multiple-image" size={20} color="#94a3b8" style={{marginRight:8}} />
                <Text style={styles.statLabel}>Files in Vault</Text>
             </View>
             <Text style={styles.statValue}>{status?.vault?.file_count || 0}</Text>
             <Text style={styles.statSub}>Total: {formatBytes(status?.vault?.total_size || 0)}</Text>
          </View>

          {/* App Updates Card */}
          <View style={styles.statCard}>
             <View style={{flexDirection:'row', alignItems:'center', justifyContent:'space-between', marginBottom: 10}}>
                <View style={{flexDirection:'row', alignItems:'center'}}>
                   <MaterialCommunityIcons name="cellphone-arrow-down" size={22} color="#38bdf8" style={{marginRight:8}} />
                   <Text style={styles.statLabel}>Actualizaciones App</Text>
                </View>
                <View style={styles.versionBadge}>
                   <Text style={styles.versionBadgeText}>v{APP_VERSION}</Text>
                </View>
             </View>

             <Text style={[styles.statSub, {marginTop: 0, marginBottom: 12}]}>
                {updateInfo?.hasUpdate 
                  ? `¡Nueva versión ${updateInfo.latestVersion} disponible!` 
                  : `Versión instalada: v${APP_VERSION} (Android)`}
             </Text>

             <TouchableOpacity 
                style={[styles.button, {paddingVertical: 12, backgroundColor: updateInfo?.hasUpdate ? '#10b981' : '#3b82f6'}]} 
                onPress={() => updateInfo?.hasUpdate ? setUpdateModalVisible(true) : handleCheckUpdate(true)}
                disabled={isCheckingUpdate}
             >
                {isCheckingUpdate ? (
                   <ActivityIndicator size="small" color="#fff" />
                ) : (
                   <View style={{flexDirection:'row', alignItems:'center', justifyContent:'center'}}>
                      <MaterialCommunityIcons 
                         name={updateInfo?.hasUpdate ? "arrow-down-bold-circle-outline" : "refresh"} 
                         size={18} 
                         color="#fff" 
                         style={{marginRight: 6}}
                      />
                      <Text style={[styles.buttonText, {fontSize: 14}]}>
                         {updateInfo?.hasUpdate ? 'Ver e Instalar Actualización' : 'Buscar Actualizaciones'}
                      </Text>
                   </View>
                )}
             </TouchableOpacity>
          </View>

          <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
             <Text style={styles.logoutText}>Cerrar Sesión y Desvincular</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Preview Modal */}
      {previewItem && (
          <Modal visible={true} transparent={true} animationType="fade" onRequestClose={() => setPreviewItem(null)}>
              <View style={styles.modalBg} {...panResponder.panHandlers}>
                  <TouchableOpacity style={[styles.modalClose, { top: Math.max(insets.top, 16) + 12 }]} onPress={() => setPreviewItem(null)}>
                      <Text style={styles.modalCloseText}>Cerrar</Text>
                  </TouchableOpacity>
                  
                  <TouchableOpacity style={styles.navBtnLeft} onPress={handlePrev}>
                      <MaterialCommunityIcons name="chevron-left" size={40} color="#fff" />
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.navBtnRight} onPress={handleNext}>
                      <MaterialCommunityIcons name="chevron-right" size={40} color="#fff" />
                  </TouchableOpacity>

                  {/* File Preview Logic */}
                  {(() => {
                      if (previewLoading && !previewSrc && !previewError) {
                          return <ActivityIndicator size="large" color="#3b82f6" />;
                      }

                      if (previewError) {
                          return (
                              <View style={styles.unsupportedCard}>
                                  <Text style={styles.unsupportedIcon}>⚠️</Text>
                                  <Text style={styles.unsupportedText}>{previewError}</Text>
                                  <TouchableOpacity style={[styles.button, {marginTop: 20}]} onPress={() => openPreview(previewItem)}>
                                      <Text style={styles.buttonText}>Reintentar</Text>
                                  </TouchableOpacity>
                              </View>
                          );
                      }

                      const name = previewItem?.name || 'archivo';
                      const ext = name.split('.').pop().toLowerCase();
                      const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext);
                      const isVideo = ['mp4', 'mov', 'm4v', 'avi', 'mkv', 'webm'].includes(ext);
                      
                      if (isImage) {
                          return (
                              <View style={styles.modalImageContainer}>
                                  {previewSrc && (
                                      <Image 
                                          source={previewSrc} 
                                          style={styles.modalImage} 
                                          resizeMode="contain" 
                                          onLoadStart={() => setPreviewLoading(true)}
                                          onLoadEnd={() => setPreviewLoading(false)}
                                          onError={() => {
                                              setPreviewLoading(false);
                                              setPreviewError("Error loading image");
                                          }}
                                      />
                                  )}
                                  {previewLoading && <ActivityIndicator size="large" color="#3b82f6" style={styles.spinner} />}
                              </View>
                          );
                      } else if (isVideo) {
                          return (
                              <View style={styles.modalImageContainer}>
                                  {previewSrc ? (
                                      <Video
                                          source={previewSrc}
                                          rate={1.0}
                                          volume={1.0}
                                          isMuted={false}
                                          resizeMode={ResizeMode.CONTAIN}
                                          shouldPlay
                                          useNativeControls
                                          style={styles.modalImage}
                                          onLoadStart={() => setPreviewLoading(true)}
                                          onLoad={() => setPreviewLoading(false)}
                                          onError={(e) => {
                                              setPreviewLoading(false);
                                              setPreviewError("Error loading video");
                                          }}
                                      />
                                  ) : (
                                       <ActivityIndicator size="large" color="#3b82f6" />
                                  )}
                                  {previewLoading && <ActivityIndicator size="large" color="#3b82f6" style={styles.spinner} />}
                              </View>
                          );
                      } else {
                          return (
                              <View style={styles.unsupportedCard}>
                                  <Text style={styles.unsupportedIcon}>📄</Text>
                                  <Text style={styles.unsupportedText}>Previsualización no disponible para .{ext}</Text>
                                  <Text style={styles.unsupportedSub}>Download the file to see its content.</Text>
                              </View>
                          );
                      }
                  })()}

                  <View style={[styles.modalActionsRow, { bottom: Math.max(insets.bottom, 16) + 25 }]}>
                      <TouchableOpacity 
                        style={[styles.modalActionCircle, (!previewSrc) && styles.buttonDisabled]} 
                        onPress={handleDownload}
                        disabled={!previewSrc}
                      >
                          <MaterialCommunityIcons name="download" size={24} color="#fff" />
                      </TouchableOpacity>
                      <TouchableOpacity style={styles.modalActionCircle} onPress={loadFileInfo}>
                          <MaterialCommunityIcons name="information-variant" size={24} color="#fff" />
                      </TouchableOpacity>
                      {role === 'admin' && (
                          <TouchableOpacity style={[styles.modalActionCircle, {backgroundColor: '#ef4444'}]} onPress={handleDeleteItem}>
                               <MaterialCommunityIcons name="trash-can-outline" size={24} color="#fff" />
                          </TouchableOpacity>
                      )}
                  </View>
              </View>
          </Modal>
      )}

      {/* Info Modal */}
      {showInfo && (
          <Modal visible={true} transparent={true} animationType="slide" onRequestClose={() => setShowInfo(false)}>
              <View style={styles.modalBg}>
                  <View style={styles.promptCard}>
                      <Text style={styles.promptTitle}>File Information</Text>
                      {infoLoading ? (
                          <ActivityIndicator size="large" color="#3b82f6" />
                      ) : fileInfo ? (
                          <View style={{ gap: 15, marginBottom: 20 }}>
                              <View>
                                  <Text style={styles.infoLabel}>Name</Text>
                                  <Text style={styles.infoValue}>{fileInfo.name}</Text>
                              </View>
                              <View>
                                  <Text style={styles.infoLabel}>Size</Text>
                                  <Text style={styles.infoValue}>{formatBytes(fileInfo.size)}</Text>
                              </View>
                              <View>
                                  <Text style={styles.infoLabel}>Date</Text>
                                  <Text style={styles.infoValue}>
                                      {fileInfo.timestamp ? fileInfo.timestamp.replace('T', ' ').replace('Z', '') : 'Unknown'}
                                  </Text>
                              </View>
                              {fileInfo.gps && (
                                  <View>
                                      <Text style={styles.infoLabel}>GPS Location</Text>
                                      <Text style={styles.infoValue}>Lat: {fileInfo.gps.lat.toFixed(6)}, Lon: {fileInfo.gps.lon.toFixed(6)}</Text>
                                  </View>
                              )}
                          </View>
                      ) : (
                          <Text style={{color: '#ef4444'}}>Could not load information.</Text>
                      )}
                      
                      <TouchableOpacity style={[styles.button, {width: '100%'}]} onPress={() => setShowInfo(false)}>
                          <Text style={styles.buttonText}>Close Info</Text>
                      </TouchableOpacity>
                  </View>
              </View>
          </Modal>
      )}

       {/* Side Menu Drawer */}
       {drawerOpen && (
           <Modal transparent={true} visible={true} animationType="none" onRequestClose={() => setDrawerOpen(false)}>
               <View style={styles.drawerContainer}>
                   <TouchableOpacity style={styles.drawerOverlay} onPress={() => setDrawerOpen(false)} />
                   <View style={[styles.drawerContent, { paddingTop: Math.max(insets.top, 16) + 20, paddingBottom: Math.max(insets.bottom, 16) + 10 }]}>
                       <View style={styles.drawerHeader}>
                           <Text style={styles.drawerTitle}>Menu</Text>
                           <TouchableOpacity onPress={() => setDrawerOpen(false)}>
                               <Text style={{color:'#64748b', fontSize: 20}}>✕</Text>
                           </TouchableOpacity>
                       </View>

                       <View style={styles.drawerUserInfo}>
                           <Text style={styles.drawerRoleLabel}>User</Text>
                           <Text style={styles.drawerRoleValue}>{role === 'admin' ? 'Administrator' : 'Standard'}</Text>
                       </View>

                       <View style={styles.drawerDivider} />

                       <TouchableOpacity 
                           style={styles.drawerItem} 
                           onPress={() => { setView('gallery'); setDrawerOpen(false); }}
                       >
                           <MaterialCommunityIcons name="image-multiple" size={24} color="#3b82f6" style={styles.drawerItemIcon} />
                           <Text style={styles.drawerItemText}>Gallery</Text>
                       </TouchableOpacity>
                       
                       <TouchableOpacity 
                           style={styles.drawerItem} 
                           onPress={() => { setView('map'); setDrawerOpen(false); }}
                       >
                           <MaterialCommunityIcons name="map" size={24} color="#10b981" style={styles.drawerItemIcon} />
                           <Text style={styles.drawerItemText}>Map Explorer</Text>
                       </TouchableOpacity>

                       <TouchableOpacity 
                           style={styles.drawerItem} 
                           onPress={() => { setView('stats'); setDrawerOpen(false); }}
                       >
                           <MaterialCommunityIcons name="monitor-dashboard" size={24} color="#3b82f6" style={styles.drawerItemIcon} />
                           <Text style={styles.drawerItemText}>Control Panel</Text>
                       </TouchableOpacity>

                       {role === 'admin' && (
                           <TouchableOpacity 
                               style={styles.drawerItem} 
                               onPress={() => { setInviteConfigModal(true); setDrawerOpen(false); }}
                           >
                               <MaterialCommunityIcons name="account-plus-outline" size={24} color="#10b981" style={styles.drawerItemIcon} />
                               <Text style={styles.drawerItemText}>Invitar User</Text>
                           </TouchableOpacity>
                       )}

                       <View style={{flex:1}} />
                       
                       <View style={styles.drawerFooter}>
                           <Text style={styles.drawerFooterText}>Vault Ingestor v1.2</Text>
                       </View>
                   </View>
               </View>
           </Modal>
       )}

       {/* Invite Configuration Modal */}
       {inviteConfigModal && (
           <Modal visible={true} transparent={true} animationType="fade">
               <View style={styles.modalBg}>
                   <View style={styles.promptCard}>
                       <Text style={styles.promptTitle}>Configure Invitation</Text>
                       <Text style={styles.promptSub}>Select the folders the guest will have access to:</Text>
                       
                       <View style={{maxHeight: 300, marginVertical: 15}}>
                           <FlatList 
                               data={['root', ...new Set(items.map(i => i.context).filter(c => c && c !== 'root'))]}
                               keyExtractor={f => f}
                               renderItem={({item: f}) => (
                                   <TouchableOpacity 
                                       style={[styles.folderSelectItem, selectedInviteFolders.includes(f) && styles.folderSelectItemActive]}
                                       onPress={() => toggleInviteFolder(f)}
                                   >
                                       <Text style={[styles.folderSelectItemText, selectedInviteFolders.includes(f) && styles.folderSelectItemTextActive]}>
                                           {f === 'root' ? 'Timeline (Everything)' : f}
                                       </Text>
                                       {selectedInviteFolders.includes(f) && <Text style={{color:'#fff'}}>✓</Text>}
                                   </TouchableOpacity>
                               )}
                           />
                       </View>

                       <View style={{flexDirection:'row', gap: 10}}>
                           <TouchableOpacity style={[styles.button, {flex:1, backgroundColor:'#334155'}]} onPress={() => setInviteConfigModal(false)}>
                               <Text style={styles.buttonText}>Cancelar</Text>
                           </TouchableOpacity>
                           <TouchableOpacity 
                               style={[styles.button, {flex:1}, selectedInviteFolders.length === 0 && styles.buttonDisabled]} 
                               onPress={handleCreateInvite}
                               disabled={selectedInviteFolders.length === 0}
                           >
                               <Text style={styles.buttonText}>Generate QR</Text>
                           </TouchableOpacity>
                       </View>
                   </View>
               </View>
           </Modal>
       )}

       {/* Invite Modal (Result) */}
       {inviteModal && inviteData && (
            <Modal visible={true} transparent={true} animationType="slide">
               <View style={styles.modalBg}>
                    <View style={[styles.qrCard, { padding: 30, backgroundColor: '#0f172a', borderColor: '#334155', borderWidth: 1, alignItems: 'center' }]}>
                        <Text style={[styles.qrTitle, { fontSize: 24, marginBottom: 10, color: '#f8fafc' }]}>Invitation Created</Text>
                        <Text style={[styles.qrText, { textAlign: 'center', color: '#94a3b8', marginBottom: 20, fontSize: 14 }]}>
                            The guest must scan this code or enter the data manually.
                        </Text>
                        
                        <View style={{ backgroundColor: '#fff', padding: 10, borderRadius: 12, marginBottom: 20 }}>
                            <Image 
                                source={{ uri: `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(JSON.stringify({url: inviteData.url, pin: inviteData.pin}))}` }} 
                                style={{ width: 180, height: 180 }} 
                                resizeMode="contain"
                            />
                        </View>

                        <View style={{ width: '100%', backgroundColor: '#1e293b', padding: 15, borderRadius: 12, marginBottom: 20, borderColor: '#334155', borderWidth: 1 }}>
                            <Text style={{ color: '#64748b', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 5 }}>Server URL</Text>
                            <Text style={{ color: '#60a5fa', fontSize: 16, fontWeight: '500', marginBottom: 15, textAlign: 'center' }} numberOfLines={2} adjustsFontSizeToFit>
                                {inviteData.url}
                            </Text>

                            <Text style={{ color: '#64748b', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 5 }}>Access PIN</Text>
                            <Text style={{ color: '#10b981', fontSize: 32, fontWeight: 'bold', letterSpacing: 4, textAlign: 'center' }}>
                                {inviteData.pin}
                            </Text>
                        </View>

                        <TouchableOpacity style={{ width: '100%', padding: 16, backgroundColor: '#3b82f6', borderRadius: 8, alignItems: 'center' }} onPress={() => setInviteModal(false)}>
                            <Text style={{color:'#fff', fontWeight:'bold', fontSize: 16}}>Accept</Text>
                        </TouchableOpacity>
                    </View>
               </View>
            </Modal>
       )}

       {/* New Folder Modal */}
       {newFolderModal && (
            <Modal visible={true} transparent={true} animationType="fade">
               <View style={styles.modalBg}>
                    <View style={styles.promptCard}>
                        <Text style={styles.promptTitle}>New Folder</Text>
                        <Text style={styles.promptSub}>Enter the name of the new folder to organize your files.</Text>
                        
                        <TextInput 
                            style={[styles.input, {marginVertical: 20, width: '100%'}]} 
                            placeholder="Folder name" 
                            placeholderTextColor="#64748b" 
                            value={newFolderName} 
                            onChangeText={setNewFolderName} 
                            autoCapitalize="none"
                            autoFocus={true}
                        />

                        <View style={{flexDirection:'row', gap: 10}}>
                            <TouchableOpacity style={[styles.button, {flex:1, backgroundColor:'#334155'}]} onPress={() => {setNewFolderModal(false); setNewFolderName('');}}>
                                <Text style={styles.buttonText}>Cancel</Text>
                            </TouchableOpacity>
                            <TouchableOpacity 
                                style={[styles.button, {flex:1}, !newFolderName.trim() && styles.buttonDisabled]} 
                                onPress={handleCreateFolder}
                                disabled={!newFolderName.trim()}
                            >
                                <Text style={styles.buttonText}>Create</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
               </View>
            </Modal>
       )}

       {/* Share Intent Modal */}
       {showShareModal && (
            <Modal visible={true} transparent={true} animationType="slide" onRequestClose={() => { setShowShareModal(false); resetShareIntent(); }}>
               <View style={styles.modalBg}>
                    <View style={[styles.promptCard, { maxWidth: 360, width: '90%', maxHeight: height * 0.8 }]}>
                        <Text style={styles.promptTitle}>📥 Save Shared Files</Text>
                        <Text style={styles.promptSub}>Choose a folder destination in your Vault.</Text>

                        {/* File previews with date editors */}
                        {shareFiles && shareFiles.length > 0 && (
                            <View style={{ maxHeight: 180, width: '100%', marginVertical: 10 }}>
                                <ScrollView nestedScrollEnabled={true}>
                                    {shareFiles.map((file, idx) => (
                                        <View key={idx} style={{ backgroundColor: '#1e293b', padding: 10, borderRadius: 8, marginBottom: 8, width: '100%' }}>
                                            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
                                                {file.mimeType?.startsWith('image') && file.path ? (
                                                    <Image source={{ uri: file.path }} style={{ width: 32, height: 32, borderRadius: 4, marginRight: 10 }} />
                                                ) : (
                                                    <MaterialCommunityIcons name="file-document" size={32} color="#94a3b8" style={{ marginRight: 10 }} />
                                                )}
                                                <View style={{ flex: 1 }}>
                                                    <Text style={{ color: '#fff', fontSize: 12 }} numberOfLines={1}>
                                                        {file.fileName || (file.path ? file.path.split('/').pop() : `shared_${Date.now()}.bin`)}
                                                    </Text>
                                                    {file.contentDate && (
                                                        <Text style={{ color: '#10b981', fontSize: 10, marginTop: 2 }}>
                                                            📅 {file.contentDate}
                                                        </Text>
                                                    )}
                                                    {file.gpsLat != null && file.gpsLon != null && (
                                                        <Text style={{ color: '#38bdf8', fontSize: 10, marginTop: 1 }}>
                                                            📍 GPS: {file.gpsLat.toFixed(4)}, {file.gpsLon.toFixed(4)}
                                                        </Text>
                                                    )}
                                                </View>
                                            </View>
                                            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                                                <MaterialCommunityIcons name="calendar-edit" size={16} color="#64748b" style={{ marginRight: 5 }} />
                                                <TextInput 
                                                    style={{ flex: 1, backgroundColor: '#0f172a', color: '#fff', fontSize: 12, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, borderWidth: 1, borderColor: '#334155' }}
                                                    placeholder="Fecha (YYYY-MM-DD HH:MM:SS)"
                                                    placeholderTextColor="#475569"
                                                    value={file.customDate}
                                                    onChangeText={(txt) => setShareFiles(prev => prev.map((f, i) => i === idx ? { ...f, customDate: txt } : f))}
                                                />
                                                <TouchableOpacity onPress={() => setShareFiles(prev => prev.map((f, i) => i === idx ? { ...f, customDate: '' } : f))} style={{ padding: 6, marginLeft: 5 }}>
                                                    <MaterialCommunityIcons name="close-circle" size={16} color="#ef4444" />
                                                </TouchableOpacity>
                                            </View>
                                        </View>
                                    ))}
                                </ScrollView>
                            </View>
                        )}

                        <Text style={{ color: '#94a3b8', fontSize: 12, fontWeight: 'bold', alignSelf: 'flex-start', marginBottom: 8 }}>Destination Folder:</Text>

                        {/* List folders */}
                        <View style={{ maxHeight: 150, width: '100%', marginBottom: 15 }}>
                            <FlatList 
                                data={['root', ...new Set(items.map(i => i.context && i.context !== 'root' ? i.context : null).filter(f => f !== null))]}
                                keyExtractor={(f) => f}
                                style={{ width: '100%' }}
                                renderItem={({ item: f }) => (
                                    <TouchableOpacity 
                                        style={{
                                            padding: 12,
                                            backgroundColor: selectedShareFolder === f ? '#1e3a8a' : '#1e293b',
                                            borderRadius: 8,
                                            marginBottom: 6,
                                            flexDirection: 'row',
                                            alignItems: 'center',
                                            borderWidth: 1,
                                            borderColor: selectedShareFolder === f ? '#3b82f6' : '#334155'
                                        }}
                                        onPress={() => setSelectedShareFolder(f)}
                                    >
                                        <MaterialCommunityIcons 
                                            name={f === 'root' ? 'calendar-clock' : 'folder-outline'} 
                                            size={18} 
                                            color={selectedShareFolder === f ? '#3b82f6' : '#94a3b8'} 
                                            style={{ marginRight: 10 }}
                                        />
                                        <Text style={{ color: '#fff', fontWeight: selectedShareFolder === f ? 'bold' : 'normal', fontSize: 13 }}>
                                            {f === 'root' ? 'Timeline (Default)' : f}
                                        </Text>
                                    </TouchableOpacity>
                                )}
                            />
                        </View>

                        {/* Progress Bar inside modal */}
                        {shareUploadState.active && (
                            <View style={{ width: '100%', marginBottom: 15, backgroundColor: '#0f172a', padding: 12, borderRadius: 8, borderWidth: 1, borderColor: '#334155' }}>
                                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                    <Text style={{ color: '#fff', fontSize: 12, fontWeight: 'bold', flex: 1, marginRight: 8 }} numberOfLines={1} ellipsizeMode="middle">
                                        ({shareUploadState.current}/{shareUploadState.total}) {shareUploadState.currentFileName || 'Archivo'}
                                    </Text>
                                    <TouchableOpacity
                                        onPress={() => {
                                            if (activeShareUploadCancelRef.current) {
                                                activeShareUploadCancelRef.current();
                                            }
                                        }}
                                        style={{ backgroundColor: '#ef4444', borderRadius: 4, paddingHorizontal: 8, paddingVertical: 2 }}
                                    >
                                        <Text style={{ color: '#fff', fontSize: 11, fontWeight: 'bold' }}>✕ Cancelar</Text>
                                    </TouchableOpacity>
                                </View>
                                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                                    <Text style={{ color: '#94a3b8', fontSize: 11 }}>{shareUploadState.statusText || 'Subiendo...'}</Text>
                                    <Text style={{ color: '#3b82f6', fontSize: 12, fontWeight: 'bold' }}>
                                        {shareUploadState.overallPercent || shareUploadState.filePercent || 0}%
                                    </Text>
                                </View>
                                <View style={{ height: 6, backgroundColor: '#334155', borderRadius: 3, overflow: 'hidden' }}>
                                    <View style={{ width: `${Math.min(100, Math.max(0, shareUploadState.overallPercent || shareUploadState.filePercent || 0))}%`, height: '100%', backgroundColor: '#3b82f6' }} />
                                </View>
                                <Text style={{ color: '#94a3b8', fontSize: 10, marginTop: 5 }}>
                                    {formatBytes(shareUploadState.fileLoadedBytes)} de {formatBytes(shareUploadState.fileTotalBytes)} ({shareUploadState.filePercent}%)
                                    {shareUploadState.total > 1 && shareUploadState.totalBatchBytes > 0 ? ` • Total: ${formatBytes(shareUploadState.totalLoadedBytes)} de ${formatBytes(shareUploadState.totalBatchBytes)}` : ''}
                                </Text>
                            </View>
                        )}

                        {/* Action buttons */}
                        <View style={{ flexDirection: 'row', gap: 10, width: '100%' }}>
                            <TouchableOpacity 
                                style={[styles.button, { flex: 1, backgroundColor: '#334155' }]} 
                                onPress={() => { setShowShareModal(false); resetShareIntent(); }}
                                disabled={shareUploadState.active}
                            >
                                <Text style={styles.buttonText}>Cancel</Text>
                            </TouchableOpacity>
                            <TouchableOpacity 
                                style={[styles.button, { flex: 1 }]} 
                                onPress={handleShareUpload}
                                disabled={shareUploadState.active}
                            >
                                <Text style={styles.buttonText}>Save</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
               </View>
            </Modal>
       )}

        {/* Custom Gallery Picker Modal */}
        <Modal visible={galleryVisible} animationType="slide" onRequestClose={() => setGalleryVisible(false)}>
          <View style={{ flex: 1, backgroundColor: '#0f172a', paddingTop: insets.top, paddingBottom: insets.bottom }}>
            <View style={styles.galleryHeader}>
              <TouchableOpacity onPress={() => setGalleryVisible(false)} style={{ padding: 10 }}>
                <MaterialCommunityIcons name="close" size={24} color="#fff" />
              </TouchableOpacity>
              <Text style={{ color: '#fff', fontSize: 18, fontWeight: 'bold' }}>Select Media</Text>
              <TouchableOpacity 
                onPress={handleConfirmGallerySelection} 
                style={{ padding: 10, opacity: selectedGalleryIds.size > 0 ? 1 : 0.5 }}
                disabled={selectedGalleryIds.size === 0}
              >
                <Text style={{ color: '#3b82f6', fontSize: 16, fontWeight: 'bold' }}>
                  Add {selectedGalleryIds.size > 0 ? `(${selectedGalleryIds.size})` : ''}
                </Text>
              </TouchableOpacity>
            </View>
            <FlatList
              data={galleryAssets}
              keyExtractor={(item) => item.id}
              numColumns={3}
              renderItem={({ item }) => {
                const isSelected = selectedGalleryIds.has(item.id);
                return (
                  <TouchableOpacity 
                    style={{ width: Dimensions.get('window').width / 3, height: Dimensions.get('window').width / 3, padding: 1 }}
                    onPress={() => toggleGalleryAsset(item.id)}
                  >
                    <Image source={{ uri: item.uri }} style={{ width: '100%', height: '100%', backgroundColor: '#1e293b' }} />
                    {item.mediaType === 'video' && (
                      <View style={{ position: 'absolute', bottom: 5, right: 5, backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 4, borderRadius: 4 }}>
                        <Text style={{ color: '#fff', fontSize: 10 }}>{Math.round(item.duration)}s</Text>
                      </View>
                    )}
                    {isSelected && (
                      <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(59, 130, 246, 0.4)', borderWidth: 3, borderColor: '#3b82f6', justifyContent: 'center', alignItems: 'center' }}>
                        <MaterialCommunityIcons name="check-circle" size={32} color="#fff" />
                      </View>
                    )}
                  </TouchableOpacity>
                );
              }}
              onEndReached={() => loadGallery(true)}
              onEndReachedThreshold={0.5}
              ListFooterComponent={galleryLoading ? <ActivityIndicator size="large" color="#3b82f6" style={{ margin: 20 }} /> : null}
            />
          </View>
        </Modal>

        {/* In-App Update Modal */}
        {updateModalVisible && updateInfo && (
          <Modal visible={true} transparent={true} animationType="slide" onRequestClose={() => !updateDownloadState.downloading && setUpdateModalVisible(false)}>
            <View style={styles.modalBg}>
              <View style={[styles.promptCard, { maxWidth: 400, width: '90%', padding: 22 }]}>
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
                  <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: '#1e3a8a', justifyContent: 'center', alignItems: 'center', marginRight: 12 }}>
                    <MaterialCommunityIcons name="rocket-launch" size={24} color="#38bdf8" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: '#fff', fontSize: 18, fontWeight: 'bold' }}>Nueva versión disponible</Text>
                    <Text style={{ color: '#38bdf8', fontSize: 13, fontWeight: '600' }}>
                      {updateInfo.latestVersion} (Actual: v{APP_VERSION})
                    </Text>
                  </View>
                </View>

                {updateInfo.apkSize > 0 && (
                  <Text style={{ color: '#94a3b8', fontSize: 12, marginBottom: 10 }}>
                    Tamaño del archivo: {formatBytes(updateInfo.apkSize)}
                  </Text>
                )}

                {/* Release notes scroll */}
                <Text style={{ color: '#cbd5e1', fontSize: 12, fontWeight: 'bold', textTransform: 'uppercase', marginBottom: 6 }}>
                  Novedades del parche:
                </Text>
                <ScrollView style={{ maxHeight: 160, backgroundColor: '#0f172a', padding: 12, borderRadius: 8, borderWidth: 1, borderColor: '#334155', marginBottom: 18 }}>
                  <Text style={{ color: '#94a3b8', fontSize: 13, lineHeight: 18 }}>
                    {updateInfo.releaseNotes}
                  </Text>
                </ScrollView>

                {/* Download progress UI */}
                {updateDownloadState.downloading && (
                  <View style={{ marginBottom: 16 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
                      <Text style={{ color: '#38bdf8', fontSize: 13, fontWeight: '600' }}>Descargando APK...</Text>
                      <Text style={{ color: '#fff', fontSize: 13, fontWeight: 'bold' }}>{updateDownloadState.percent}%</Text>
                    </View>
                    <View style={styles.progressBarBg}>
                      <View style={[styles.progressBarFill, { width: `${updateDownloadState.percent}%`, backgroundColor: '#38bdf8' }]} />
                    </View>
                    <Text style={{ color: '#64748b', fontSize: 11, textAlign: 'center', marginTop: 4 }}>
                      {formatBytes(updateDownloadState.downloadedBytes)} de {formatBytes(updateDownloadState.totalBytes)}
                    </Text>
                  </View>
                )}

                {/* Download Completed UI */}
                {updateDownloadState.downloadedUri && (
                  <View style={{ backgroundColor: '#064e3b', padding: 12, borderRadius: 8, marginBottom: 16, borderWidth: 1, borderColor: '#059669' }}>
                    <Text style={{ color: '#34d399', fontSize: 13, fontWeight: '600', textAlign: 'center' }}>
                      APK descargado correctamente. Pulsa "Instalar ahora" para continuar.
                    </Text>
                  </View>
                )}

                {/* Error message if any */}
                {updateDownloadState.error && (
                  <View style={{ backgroundColor: '#450a0a', padding: 10, borderRadius: 8, marginBottom: 16, borderWidth: 1, borderColor: '#dc2626' }}>
                    <Text style={{ color: '#f87171', fontSize: 12, textAlign: 'center' }}>
                      Error: {updateDownloadState.error}
                    </Text>
                  </View>
                )}

                {/* Action buttons */}
                <View style={{ flexDirection: 'row', gap: 10 }}>
                  {updateDownloadState.downloading ? (
                    <TouchableOpacity 
                      style={[styles.button, { flex: 1, backgroundColor: '#ef4444' }]} 
                      onPress={handleCancelUpdateDownload}
                    >
                      <Text style={styles.buttonText}>Cancelar</Text>
                    </TouchableOpacity>
                  ) : updateDownloadState.downloadedUri ? (
                    <>
                      <TouchableOpacity 
                        style={[styles.button, { flex: 1, backgroundColor: '#334155' }]} 
                        onPress={() => setUpdateModalVisible(false)}
                        disabled={isInstalling}
                      >
                        <Text style={styles.buttonText}>Cerrar</Text>
                      </TouchableOpacity>
                      <TouchableOpacity 
                        style={[styles.button, { flex: 1, backgroundColor: '#10b981', opacity: isInstalling ? 0.7 : 1 }]} 
                        onPress={() => handleInstallUpdate()}
                        disabled={isInstalling}
                      >
                        {isInstalling ? (
                          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center' }}>
                            <ActivityIndicator size="small" color="#fff" style={{ marginRight: 6 }} />
                            <Text style={styles.buttonText}>Instalando...</Text>
                          </View>
                        ) : (
                          <Text style={styles.buttonText}>Instalar ahora</Text>
                        )}
                      </TouchableOpacity>
                    </>
                  ) : (
                    <>
                      <TouchableOpacity 
                        style={[styles.button, { flex: 1, backgroundColor: '#334155' }]} 
                        onPress={() => setUpdateModalVisible(false)}
                      >
                        <Text style={styles.buttonText}>Más tarde</Text>
                      </TouchableOpacity>
                      <TouchableOpacity 
                        style={[styles.button, { flex: 1, backgroundColor: '#3b82f6' }]} 
                        onPress={handleStartDownloadUpdate}
                      >
                        <Text style={styles.buttonText}>Actualizar</Text>
                      </TouchableOpacity>
                    </>
                  )}
                </View>
              </View>
            </View>
          </Modal>
        )}

    </View>
  );
}

const getMapHtml = () => `
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
    <style>
        body { padding: 0; margin: 0; background-color: #0f172a; }
        #map { height: 100vh; width: 100vw; }
        .leaflet-container { background: #0f172a; }
    </style>
</head>
<body>
    <div id="map"></div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
    <script>
        var map;
        var markers;
        
        function initMap() {
            map = L.map('map').setView([0, 0], 2);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; CARTO',
                subdomains: 'abcd',
                maxZoom: 20
            }).addTo(map);
            
            markers = L.markerClusterGroup({
                showCoverageOnHover: false,
                maxClusterRadius: 50
            });
            
            if (window.mapData && window.mapData.length > 0) {
                var bounds = L.latLngBounds();
                window.mapData.forEach(function(item) {
                    if (item.gps && item.gps.lat != null && item.gps.lon != null) {
                        var latlng = [item.gps.lat, item.gps.lon];
                        bounds.extend(latlng);
                        
                        var marker = L.marker(latlng);
                        marker.on('click', function() {
                            window.ReactNativeWebView.postMessage(JSON.stringify({ action: 'openPreview', id: item.id }));
                        });
                        markers.addLayer(marker);
                    }
                });
                map.addLayer(markers);
                if (bounds.isValid()) {
                    map.fitBounds(bounds, { padding: [20, 20], maxZoom: 15 });
                }
            }
        }
    </script>
</body>
</html>
`;

export function Thumbnail({ item, onPress, onLongPress, customWidth, showContextTag, selectionMode, isSelected }) {
    const [src, setSrc] = useState(null);
    const [failed, setFailed] = useState(false);
    
    const name = item?.name || 'archivo';
    const ext = name.split('.').pop().toLowerCase();
    const isVideo = ['mp4', 'mov', 'm4v', 'avi', 'mkv', 'webm'].includes(ext);

    useEffect(() => {
        api.getThumbUrl(item)
            .then(s => setSrc(s))
            .catch(() => setFailed(true));
    }, [item]);

    const renderOverlay = () => {
        if (isVideo) {
            return (
                <View style={styles.videoOverlay}>
                    <Text style={styles.videoIcon}>▶</Text>
                </View>
            );
        }
        return null;
    };

    if (failed || !src) {
        return (
            <TouchableOpacity style={[styles.imageContainer, customWidth && { width: customWidth, height: customWidth }, selectionMode && !isSelected && { opacity: 0.5 }]} onPress={onPress} onLongPress={onLongPress}>
                <View style={styles.filePlaceholder}>
                    <Text style={styles.fileIcon}>{isVideo ? '🎬' : '📄'}</Text>
                    <Text style={styles.fileNameText} numberOfLines={2}>{item.name}</Text>
                </View>
                {isSelected && (
                    <View style={styles.selectedOverlay}>
                        <MaterialCommunityIcons name="check-circle" size={24} color="#3b82f6" />
                    </View>
                )}
            </TouchableOpacity>
        );
    }

    return (
        <TouchableOpacity style={[styles.imageContainer, customWidth && { width: customWidth, height: customWidth }, selectionMode && !isSelected && { opacity: 0.5 }]} onPress={onPress} onLongPress={onLongPress}>
            <Image 
                source={src} 
                style={styles.thumbnail} 
                resizeMode="cover" 
                onError={() => setFailed(true)}
            />
            {renderOverlay()}
            {showContextTag && (
                <View style={styles.contextTag}>
                    <Text style={styles.contextTagText} numberOfLines={1}>{item.context}</Text>
                </View>
            )}
            {isSelected && (
                <View style={styles.selectedOverlay}>
                    <MaterialCommunityIcons name="check-circle" size={24} color="#3b82f6" />
                </View>
            )}
        </TouchableOpacity>
    );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  content: { padding: 30, justifyContent: 'center', flex: 1 },
  title: { fontSize: 28, fontWeight: 'bold', color: '#fff', marginBottom: 5 },
  subtitle: { fontSize: 16, color: '#94a3b8', marginBottom: 40 },
  input: { backgroundColor: '#1e293b', borderRadius: 12, padding: 15, color: '#fff', marginBottom: 15, borderWidth: 1, borderColor: '#334155' },
  inputPin: { backgroundColor: '#1e293b', borderRadius: 12, padding: 15, color: '#3b82f6', fontSize: 24, fontWeight: 'bold', textAlign: 'center', marginBottom: 25, borderWidth: 1, borderColor: '#3b82f6' },
  button: { backgroundColor: '#3b82f6', borderRadius: 12, padding: 18, alignItems: 'center' },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  buttonScan: { backgroundColor: '#10b981', borderRadius: 12, padding: 18, alignItems: 'center', marginBottom: 20 },
  buttonDisabled: { backgroundColor: '#475569' },
  errorText: { color: '#ef4444', marginBottom: 15, textAlign: 'center', fontWeight: 'bold' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingBottom: 15, borderBottomWidth: 1, borderBottomColor: '#1e293b' },
  headerTitle: { fontSize: 22, fontWeight: 'bold', color: '#fff' },
  folderSelectorContainer: { borderBottomWidth: 1, borderBottomColor: '#1e293b' },
  folderSelector: { flexDirection: 'row', alignItems: 'center', padding: 10 },
  addFolderBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: '#3b82f6', justifyContent: 'center', alignItems: 'center', marginLeft: 10 },
  addFolderText: { color: '#fff', fontSize: 20, fontWeight: 'bold' },
  folderChip: { paddingHorizontal: 15, paddingVertical: 8, borderRadius: 20, backgroundColor: '#1e293b', marginRight: 10, borderWidth: 1, borderColor: '#334155' },
  folderChipActive: { backgroundColor: '#3b82f6', borderColor: '#3b82f6' },
  folderChipText: { color: '#94a3b8', fontSize: 13, fontWeight: '600' },
  folderChipTextActive: { color: '#fff' },
  filterBar: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 15, paddingBottom: 10 },
  filterLabel: { color: '#64748b', fontSize: 11, fontWeight: 'bold', marginRight: 10 },
  filterOpt: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 4, backgroundColor: '#0f172a', marginRight: 5 },
  filterOptActive: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 4, backgroundColor: '#1e293b', marginRight: 5 },
  filterOptText: { color: '#475569', fontSize: 11 },
  filterOptTextActive: { color: '#3b82f6', fontSize: 11, fontWeight: 'bold' },
  folderActions: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 15, paddingBottom: 10 },
  folderPathText: { color: '#64748b', fontSize: 11 },
  deleteFolderBtn: { padding: 5 },
  deleteFolderText: { color: '#ef4444', fontSize: 11, fontWeight: 'bold' },
  gallery: { padding: 2, paddingBottom: 100 },
  imageContainer: { margin: 2, width: ITEM_WIDTH, height: ITEM_WIDTH, borderRadius: 8, overflow: 'hidden', backgroundColor: '#1e293b' },
  thumbnail: { width: '100%', height: '100%' },
  statsContainer: { padding: 20, gap: 15 },
  statCard: { backgroundColor: '#1e293b', padding: 20, borderRadius: 16, borderWidth: 1, borderColor: '#334155' },
  statLabel: { color: '#94a3b8', fontSize: 14, textTransform: 'uppercase', fontWeight: 'bold', marginBottom: 5 },
  statValue: { color: '#fff', fontSize: 32, fontWeight: 'bold' },
  statSub: { color: '#64748b', fontSize: 12, marginTop: 5 },
  logoutButton: { marginTop: 40, padding: 20, alignItems: 'center', borderWidth: 1, borderColor: '#ef4444', borderRadius: 12 },
  logoutText: { color: '#ef4444', fontWeight: 'bold' },
  divider: { marginVertical: 20, alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#1e293b' },
  dividerText: { backgroundColor: '#0f172a', paddingHorizontal: 10, position: 'absolute', top: -10, color: '#64748b', fontSize: 11, fontWeight: 'bold' },
  scannerOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center' },
  scannerBox: { width: 250, height: 250, borderWidth: 2, borderColor: '#3b82f6', borderRadius: 12 },
  fabContainer: { position: 'absolute', right: 25, alignItems: 'center', zIndex: 999, elevation: 10 },
  fab: { width: 60, height: 60, borderRadius: 30, backgroundColor: '#3b82f6', justifyContent: 'center', alignItems: 'center', shadowColor: '#000', shadowOffset: {width:0,height:4}, shadowOpacity:0.3, shadowRadius:4, elevation:8, zIndex: 1000 },
  fabIcon: { fontSize: 28, color: '#fff' },
  galleryHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 15, borderBottomWidth: 1, borderBottomColor: '#1e293b', backgroundColor: '#0f172a' },
  modalBg: { flex: 1, backgroundColor: 'rgba(0,0,0,0.9)', justifyContent: 'center', alignItems: 'center' },
  modalClose: { position: 'absolute', right: 20, zIndex: 10, padding: 10, backgroundColor: '#1e293b', borderRadius: 8 },
  modalCloseText: { color: '#fff', fontWeight: 'bold' },
  modalImage: { width: '100%', height: '100%' },
  modalImageContainer: { width: '90%', height: '70%', borderRadius: 12, overflow: 'hidden', backgroundColor: '#1e293b', justifyContent: 'center', alignItems: 'center' },
  spinner: { position: 'absolute' },
  modalActionsRow: { flexDirection: 'row', gap: 15, position: 'absolute', width: '90%', justifyContent: 'center' },
  modalSmallBtn: { flex: 1, maxWidth: 180, backgroundColor: '#3b82f6', padding: 18, borderRadius: 16, alignItems: 'center' },
  modalActionCircle: { width: 60, height: 60, borderRadius: 30, backgroundColor: '#3b82f6', justifyContent: 'center', alignItems: 'center', shadowColor: '#000', shadowOffset: {width:0,height:2}, shadowOpacity:0.3, shadowRadius:4, elevation:5 },
  promptCard: { backgroundColor: '#1e293b', padding: 25, borderRadius: 16, width: '85%', borderWidth: 1, borderColor: '#334155' },
  promptTitle: { color: '#fff', fontSize: 18, fontWeight: 'bold', marginBottom: 20 },
  qrCard: { backgroundColor: '#fff', padding: 30, borderRadius: 24, width: '85%', alignItems: 'center' },
  qrTitle: { fontSize: 22, fontWeight: 'bold', color: '#0f172a', marginBottom: 15 },
  qrText: { textAlign:'center', color:'#475569', marginBottom: 20 },
  qrPin: { fontSize: 40, fontWeight: 'bold', color: '#3b82f6', letterSpacing: 5 },
  filePlaceholder: { flex: 1, backgroundColor: '#1e293b', justifyContent: 'center', alignItems: 'center', padding: 10 },
  fileIcon: { fontSize: 32, marginBottom: 5 },
  fileNameText: { color: '#94a3b8', fontSize: 10, textAlign: 'center', fontWeight: 'bold' },
  videoOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.3)', justifyContent: 'center', alignItems: 'center' },
  videoIcon: { color: '#fff', fontSize: 24, opacity: 0.8 },
  selectedOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(59, 130, 246, 0.3)', justifyContent: 'center', alignItems: 'center', borderWidth: 2, borderColor: '#3b82f6', borderRadius: 8 },
  unsupportedCard: { backgroundColor: '#1e293b', padding: 40, borderRadius: 20, alignItems: 'center', width: '80%' },
  unsupportedIcon: { fontSize: 64, marginBottom: 20 },
  unsupportedText: { color: '#fff', fontSize: 18, fontWeight: 'bold', textAlign: 'center' },
  unsupportedSub: { color: '#64748b', fontSize: 14, marginTop: 10, textAlign: 'center' },
  contextTag: { position: 'absolute', top: 4, right: 4, backgroundColor: 'rgba(59, 130, 246, 0.9)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, maxWidth: '80%' },
  contextTagText: { color: '#fff', fontSize: 8, fontWeight: 'bold' },
  // Drawer Styles
  drawerContainer: { flex: 1, flexDirection: 'row' },
  drawerOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)' },
  drawerContent: { width: 280, height: '100%', backgroundColor: '#1e293b', paddingHorizontal: 25 },
  drawerHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 40 },
  drawerTitle: { fontSize: 24, fontWeight: 'bold', color: '#fff' },
  drawerUserInfo: { marginBottom: 30 },
  drawerRoleLabel: { color: '#64748b', fontSize: 12, textTransform: 'uppercase', marginBottom: 5 },
  drawerRoleValue: { color: '#fff', fontSize: 18, fontWeight: 'bold' },
  drawerDivider: { height: 1, backgroundColor: '#334155', marginBottom: 20 },
  drawerItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: 18, paddingHorizontal: 15, marginBottom: 8, backgroundColor: '#2d3748', borderRadius: 12 },
  drawerItemIcon: { marginRight: 15 },
  drawerItemText: { color: '#e2e8f0', fontSize: 16, fontWeight: 'bold' },
  drawerFooter: { borderTopWidth: 1, borderTopColor: '#334155', paddingTop: 20, alignItems: 'center' },
  drawerFooterText: { color: '#475569', fontSize: 12 },
  // Stats Progress Bar
  progressBarBg: { height: 8, backgroundColor: '#0f172a', borderRadius: 4, marginVertical: 10, overflow: 'hidden' },
  progressBarFill: { height: '100%', borderRadius: 4 },
  // Extra
  promptSub: { color: '#94a3b8', fontSize: 14, marginBottom: 10 },
  folderSelectItem: { flexDirection:'row', justifyContent:'space-between', padding: 15, backgroundColor: '#0f172a', borderRadius: 8, marginBottom: 8 },
  folderSelectItemActive: { backgroundColor: '#3b82f6' },
  folderSelectItemText: { color: '#94a3b8' },
  folderSelectItemTextActive: { color: '#fff', fontWeight: 'bold' },
  
  // New Styles for Timeline & Folders
  typeMarkerContainer: { flexDirection: 'row', alignItems: 'center', width: '100%', paddingHorizontal: 15, marginVertical: 15 },
  typeMarkerText: { color: '#64748b', fontSize: 12, fontWeight: 'bold', marginRight: 10, backgroundColor: '#0f172a', paddingRight: 10 },
  typeMarkerLine: { flex: 1, height: 1, backgroundColor: '#1e293b' },
  
  rowContainer: { flexDirection: 'row' },
  rowItemsContainer: { flex: 1, flexDirection: 'row', justifyContent: 'flex-start' },
  
  sideMarkerContainer: { width: 45, alignItems: 'center', marginRight: 5 },
  sideMarkerContent: { alignItems: 'center', flex: 1 },
  sideMarkerDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#3b82f6', marginTop: 10 },
  sideMarkerText: { color: '#94a3b8', fontSize: 10, fontWeight: 'bold', marginTop: 5, textAlign: 'center' },
  sideMarkerLine: { width: 2, flex: 1, backgroundColor: '#1e293b', marginTop: 5 },
  
  folderCard: { margin: 2, borderRadius: 8, backgroundColor: '#1e293b', borderWidth: 1, borderColor: '#334155', justifyContent: 'center', alignItems: 'center', padding: 5 },
  folderCardTitle: { color: '#fff', fontSize: 12, fontWeight: 'bold', marginTop: 5, textAlign: 'center' },
  folderCardSub: { color: '#64748b', fontSize: 9, marginTop: 2 },
  
  sortMenuBtn: { flexDirection: 'row', alignItems: 'center', marginLeft: 15, backgroundColor: '#1e293b', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, borderWidth: 1, borderColor: '#334155' },
  sortMenuBtnText: { color: '#94a3b8', fontSize: 11, fontWeight: 'bold' },
  sortMenuDropdown: { position: 'absolute', top: 30, left: 100, backgroundColor: '#1e293b', borderRadius: 8, borderWidth: 1, borderColor: '#334155', padding: 5, zIndex: 100, elevation: 10, shadowColor: '#000', shadowOffset: {width: 0, height: 4}, shadowOpacity: 0.3, shadowRadius: 4 },
  sortMenuItem: { flexDirection: 'row', alignItems: 'center', padding: 10, minWidth: 120 },
  sortMenuItemText: { color: '#cbd5e1', fontSize: 12, fontWeight: 'bold' },
  
  // Navigation & Info Styles
  navBtnLeft: { position: 'absolute', left: 10, top: '45%', zIndex: 10, padding: 10, backgroundColor: 'rgba(30, 41, 59, 0.6)', borderRadius: 30 },
  navBtnRight: { position: 'absolute', right: 10, top: '45%', zIndex: 10, padding: 10, backgroundColor: 'rgba(30, 41, 59, 0.6)', borderRadius: 30 },
  infoLabel: { color: '#64748b', fontSize: 12, textTransform: 'uppercase', fontWeight: 'bold', marginBottom: 2 },
  infoValue: { color: '#fff', fontSize: 16 },
  
  // App Version Badge
  versionBadge: { backgroundColor: '#1e3a8a', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12, borderWidth: 1, borderColor: '#38bdf8' },
  versionBadgeText: { color: '#38bdf8', fontSize: 11, fontWeight: 'bold' },

  uploadMenu: { position: 'absolute', bottom: 70, right: 0, backgroundColor: '#1e293b', borderRadius: 12, padding: 8, borderWidth: 1, borderColor: '#334155', elevation: 12, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.25, shadowRadius: 3.84, minWidth: 160, zIndex: 1001 },
  uploadMenuItem: { flexDirection: 'row', alignItems: 'center', padding: 12, gap: 10 },
  uploadMenuText: { color: '#fff', fontSize: 14, fontWeight: '500' },
});

export default function App() {
  return (
    <SafeAreaProvider>
      <MainApp />
    </SafeAreaProvider>
  );
}
