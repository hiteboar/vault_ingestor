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
  SafeAreaView,
  StatusBar,
  Dimensions,
  Modal,
  Alert,
  PanResponder
} from 'react-native';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Video, ResizeMode } from 'expo-av';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import * as api from './api';
import { AppState } from 'react-native';
import { useShareIntent } from 'expo-share-intent';

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

export default function App() {
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('gallery'); // 'gallery' or 'stats'
  
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
  const [uploadMenuVisible, setUploadMenuVisible] = useState(false);
  const [uploadState, setUploadState] = useState({ active: false, current: 0, total: 0, percent: 0 });
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
  const [shareUploadState, setShareUploadState] = useState({ active: false, current: 0, total: 0, percent: 0 });
  const [selectedShareFolder, setSelectedShareFolder] = useState('root');
  
  // Date filters for timeline
  const [selectedYear, setSelectedYear] = useState('All');
  const [selectedMonth, setSelectedMonth] = useState('All');
  
  // UI - Drawer & Refresh
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [inviteConfigModal, setInviteConfigModal] = useState(false);
  const [selectedInviteFolders, setSelectedInviteFolders] = useState(['root']);
  const [lastUpdated, setLastUpdated] = useState(new Date());

  useEffect(() => {
    checkConnection();
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
        setError('Connection error or token revoked.');
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

      setUploadState({ active: true, current: 0, total: assets.length, percent: 0 });
      let successCount = 0;
      
      for (let i = 0; i < assets.length; i++) {
          const asset = assets[i];
          const filename = asset.name || asset.fileName || asset.uri.split('/').pop() || 'upload.bin';
          setUploadState(prev => ({ ...prev, current: i + 1, percent: 0 }));
          
          try {
              const fileInfo = await FileSystem.getInfoAsync(asset.uri);
              // Prioritize asset.creationTime (from ImagePicker) then fileInfo.modificationTime
              const rawTimestamp = asset.creationTime || fileInfo.modificationTime;
              const originalDate = rawTimestamp 
                  ? new Date(rawTimestamp * (rawTimestamp > 1e11 ? 1 : 1000)).toISOString()
                  : null;
                  
              await api.uploadFile(asset.uri, filename, asset.mimeType || asset.type || 'application/octet-stream', currentFolder, originalDate, (pct) => {
                  setUploadState(prev => ({ ...prev, percent: pct }));
              });
              successCount++;
          } catch(e) {
              alert(`Error uploading ${filename}: ${e.message}`);
          }
      }
      
      setUploadState({ active: false, current: 0, total: 0, percent: 0 });
      loadData();
      if (successCount > 0 && successCount < assets.length) {
          alert(`Uploaded ${successCount} of ${assets.length} files successfully.`);
      }
  };

  const handleShareUpload = async () => {
      if (!shareIntent || !shareIntent.files || shareIntent.files.length === 0) return;
      
      const assets = shareIntent.files;
      setShareUploadState({ active: true, current: 0, total: assets.length, percent: 0 });
      let successCount = 0;

      for (let i = 0; i < assets.length; i++) {
          const asset = assets[i];
          const filename = asset.fileName || asset.path.split('/').pop() || `shared_${Date.now()}.bin`;
          setShareUploadState(prev => ({ ...prev, current: i + 1, percent: 0 }));
          
          try {
              let originalDate = null;
              try {
                  // On Android, asset.contentUri points to the original system content provider file.
                  // Querying contentUri via FileSystem.getInfoAsync returns the original modification time,
                  // whereas asset.path points to the newly created temporary cache file.
                  const queryPath = asset.contentUri || asset.path;
                  const fileUri = (queryPath.startsWith('file://') || queryPath.startsWith('content://'))
                      ? queryPath
                      : `file://${queryPath}`;
                  const fileInfo = await FileSystem.getInfoAsync(fileUri);
                  if (fileInfo && fileInfo.modificationTime) {
                      originalDate = new Date(fileInfo.modificationTime * 1000).toISOString();
                  }
              } catch (fsErr) {
                  // Ignorar errores al consultar metadatos del archivo temporal o contentUri
              }

              await api.uploadFile(
                  asset.path, 
                  filename, 
                  asset.type || 'application/octet-stream', 
                  selectedShareFolder, 
                  originalDate, 
                  (pct) => {
                      setShareUploadState(prev => ({ ...prev, percent: pct }));
                  }
              );
              successCount++;
          } catch(e) {
              alert(`Error uploading shared file ${filename}: ${e.message}`);
          }
      }

      setShareUploadState({ active: false, current: 0, total: 0, percent: 0 });
      setShowShareModal(false);
      resetShareIntent();
      loadData();
      
      if (successCount === assets.length) {
          Alert.alert("Success", "All shared files uploaded successfully!");
      } else if (successCount > 0) {
          Alert.alert("Partial Success", `Uploaded ${successCount} of ${assets.length} files successfully.`);
      }
  };

  const handlePickDocument = async () => {
    const result = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, multiple: true });
    if (!result.canceled && result.assets && result.assets.length > 0) {
      processUploads(result.assets);
    }
  };

  const handlePickMedia = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.All,
      allowsMultipleSelection: true,
      quality: 1,
    });
    if (!result.canceled && result.assets && result.assets.length > 0) {
      processUploads(result.assets);
    }
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
                          return (
                              <TouchableOpacity 
                                  key={item.id} 
                                  style={[styles.folderCard, { width: rowItemWidth, height: rowItemWidth }]}
                                  onPress={() => setCurrentFolder(item.name)}
                              >
                                  <MaterialCommunityIcons name="folder-multiple" size={32} color="#3b82f6" />
                                  <Text style={styles.folderCardTitle} numberOfLines={1}>{item.name}</Text>
                                  <Text style={styles.folderCardSub}>
                                      {item.date_range?.newest ? item.date_range.newest.split('T')[0] : ''}
                                  </Text>
                              </TouchableOpacity>
                          );
                      } else {
                          return (
                              <Thumbnail 
                                  key={item.id}
                                  item={item} 
                                  onPress={() => openPreview(item)} 
                                  customWidth={rowItemWidth}
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
              if (i.context !== 'root') return false;
              if (selectedYear !== 'All') {
                  if (!i.timestamp.startsWith(selectedYear)) return false;
              }
              return true;
          }
          return i.context === currentFolder;
      });

      if (currentFolder === 'root') {
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
      <View style={styles.container}>
        <ActivityIndicator size="large" color="#3b82f6" />
      </View>
    );
  }

  if (!connected) {
      // (Scan & Login UI... omitted largely unchanged but simplified for space)
      if (showScanner) {
        return (
          <SafeAreaView style={styles.container}>
            <CameraView 
              style={StyleSheet.absoluteFillObject}
              facing="back"
              onBarcodeScanned={scanned ? undefined : handleBarcodeScanned}
              barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
            />
            <View style={styles.scannerOverlay}>
               <View style={styles.scannerBox} />
               <TouchableOpacity style={styles.buttonCancelScanner} onPress={() => setShowScanner(false)}>
                 <Text style={styles.buttonText}>Cancel Scan</Text>
               </TouchableOpacity>
            </View>
          </SafeAreaView>
        );
      }
  
      return (
        <SafeAreaView style={styles.container}>
          <StatusBar barStyle="light-content" />
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
        </SafeAreaView>
      );
  }

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" />       
      {/* Header */}
      <View style={styles.header}>
        <View style={{flexDirection: 'row', alignItems: 'center'}}>
            {view === 'stats' && (
                <TouchableOpacity onPress={() => setView('gallery')} style={{marginRight:15}}>
                    <MaterialCommunityIcons name="arrow-left" size={28} color="#3b82f6" />
                </TouchableOpacity>
            )}
            <Text style={styles.headerTitle}>{view === 'stats' ? 'Control Panel' : 'Vault Ingestor'}</Text>
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

      {/* Folder Selector & Management */}
      {view === 'gallery' && (
        <View style={styles.folderSelectorContainer}>
            <View style={styles.folderSelector}>
                <FlatList 
                    horizontal
                    showsHorizontalScrollIndicator={false}
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
                {role === 'admin' && (
                    <TouchableOpacity style={styles.addFolderBtn} onPress={() => setNewFolderModal(true)}>
                        <MaterialCommunityIcons name="plus" size={24} color="#fff" />
                    </TouchableOpacity>
                )}
            </View>

            {/* Timeline Filters (Year/Month) */}
            {currentFolder === 'root' && (
                <View style={styles.filterBar}>
                    <Text style={styles.filterLabel}>Filter:</Text>
                    <FlatList 
                        horizontal
                        showsHorizontalScrollIndicator={false}
                        data={['All', ...new Set(items.filter(i => i.context === 'root').map(i => (i.timestamp || '').split('-')[0]).filter(y => y))]}

                        keyExtractor={y => y}
                        renderItem={({item: y}) => (
                           <TouchableOpacity onPress={() => setSelectedYear(y)} style={selectedYear === y ? styles.filterOptActive : styles.filterOpt}>
                               <Text style={selectedYear === y ? styles.filterOptTextActive : styles.filterOptText}>{y}</Text>
                           </TouchableOpacity>
                        )}
                    />
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
                <View style={{ position: 'absolute', bottom: 85, left: 15, right: 15, backgroundColor: '#1e293b', padding: 15, borderRadius: 12, borderWidth: 1, borderColor: '#334155', elevation: 5, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.25, shadowRadius: 3.84 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
                        <Text style={{ color: '#fff', fontSize: 14, fontWeight: 'bold' }}>
                            Uploading file {uploadState.current} of {uploadState.total}...
                        </Text>
                        <Text style={{ color: '#3b82f6', fontSize: 14, fontWeight: 'bold' }}>{uploadState.percent}%</Text>
                    </View>
                    <View style={{ height: 6, backgroundColor: '#334155', borderRadius: 3, overflow: 'hidden' }}>
                        <View style={{ width: `${uploadState.percent}%`, height: '100%', backgroundColor: '#3b82f6' }} />
                    </View>
                </View>
            )}

            {/* Subida Flotante */}
            <View style={styles.fabContainer}>
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

          <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
             <Text style={styles.logoutText}>Cerrar Sesión y Desvincular</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Preview Modal */}
      {previewItem && (
          <Modal visible={true} transparent={true} animationType="fade" onRequestClose={() => setPreviewItem(null)}>
              <View style={styles.modalBg} {...panResponder.panHandlers}>
                  <TouchableOpacity style={styles.modalClose} onPress={() => setPreviewItem(null)}>
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

                  <View style={styles.modalActionsRow}>
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
                   <View style={styles.drawerContent}>
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

                        {/* File preview and count */}
                        {shareIntent.files && shareIntent.files.length > 0 && (
                            <View style={{ backgroundColor: '#1e293b', padding: 12, borderRadius: 8, marginVertical: 15, width: '100%', flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                                {shareIntent.files[0].type?.startsWith('image') ? (
                                    <Image 
                                        source={{ uri: shareIntent.files[0].path }} 
                                        style={{ width: 48, height: 48, borderRadius: 6, backgroundColor: '#0f172a' }}
                                    />
                                ) : (
                                    <View style={{ width: 48, height: 48, borderRadius: 6, backgroundColor: '#0f172a', alignItems: 'center', justifyContent: 'center' }}>
                                        <MaterialCommunityIcons name="file-document" size={24} color="#94a3b8" />
                                    </View>
                                )}
                                <View style={{ flex: 1 }}>
                                    <Text style={{ color: '#fff', fontSize: 13, fontWeight: 'bold' }} numberOfLines={1}>
                                        {shareIntent.files[0].fileName || shareIntent.files[0].path.split('/').pop()}
                                    </Text>
                                    <Text style={{ color: '#64748b', fontSize: 11 }}>
                                        {shareIntent.files.length > 1 ? `And ${shareIntent.files.length - 1} more file(s)` : 'Ready to upload'}
                                    </Text>
                                </View>
                            </View>
                        )}

                        <Text style={{ color: '#94a3b8', fontSize: 12, fontWeight: 'bold', alignSelf: 'flex-start', marginBottom: 8 }}>Destination Folder:</Text>

                        {/* List folders */}
                        <View style={{ maxHeight: 220, width: '100%', marginBottom: 20 }}>
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
                            <View style={{ width: '100%', marginBottom: 15 }}>
                                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5 }}>
                                    <Text style={{ color: '#fff', fontSize: 12 }}>Uploading {shareUploadState.current} of {shareUploadState.total}...</Text>
                                    <Text style={{ color: '#3b82f6', fontSize: 12, fontWeight: 'bold' }}>{shareUploadState.percent}%</Text>
                                </View>
                                <View style={{ height: 4, backgroundColor: '#334155', borderRadius: 2, overflow: 'hidden' }}>
                                    <View style={{ width: `${shareUploadState.percent}%`, height: '100%', backgroundColor: '#3b82f6' }} />
                                </View>
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

    </SafeAreaView>
  );
}

// Componente helper para cargar thmbnails resolviendo sus Headers
function Thumbnail({ item, onPress, customWidth }) {
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
            <TouchableOpacity style={[styles.imageContainer, customWidth && { width: customWidth, height: customWidth }]} onPress={onPress}>
                <View style={styles.filePlaceholder}>
                    <Text style={styles.fileIcon}>{isVideo ? '🎬' : '📄'}</Text>
                    <Text style={styles.fileNameText} numberOfLines={2}>{item.name}</Text>
                </View>
            </TouchableOpacity>
        );
    }

    return (
        <TouchableOpacity style={[styles.imageContainer, customWidth && { width: customWidth, height: customWidth }]} onPress={onPress}>
            <Image 
                source={src} 
                style={styles.thumbnail} 
                resizeMode="cover" 
                onError={() => setFailed(true)}
            />
            {renderOverlay()}
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
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20, paddingTop: 50, borderBottomWidth: 1, borderBottomColor: '#1e293b' },
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
  buttonCancelScanner: { position: 'absolute', bottom: 50, backgroundColor: '#ef4444', padding: 15, borderRadius: 12, paddingHorizontal: 30 },
  fabContainer: { position: 'absolute', bottom: 30, right: 30, alignItems: 'center' },
  fab: { width: 60, height: 60, borderRadius: 30, backgroundColor: '#3b82f6', justifyContent: 'center', alignItems: 'center', shadowColor: '#000', shadowOffset: {width:0,height:4}, shadowOpacity:0.3, shadowRadius:4, elevation:5 },
  fabIcon: { fontSize: 28, color: '#fff' },
  modalBg: { flex: 1, backgroundColor: 'rgba(0,0,0,0.9)', justifyContent: 'center', alignItems: 'center' },
  modalClose: { position: 'absolute', top: 50, right: 20, zIndex: 10, padding: 10, backgroundColor: '#1e293b', borderRadius: 8 },
  modalCloseText: { color: '#fff', fontWeight: 'bold' },
  modalImage: { width: '100%', height: '100%' },
  modalImageContainer: { width: '90%', height: '70%', borderRadius: 12, overflow: 'hidden', backgroundColor: '#1e293b', justifyContent: 'center', alignItems: 'center' },
  spinner: { position: 'absolute' },
  modalActionsRow: { flexDirection: 'row', gap: 15, position: 'absolute', bottom: 50, width: '90%', justifyContent: 'center' },
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
  unsupportedCard: { backgroundColor: '#1e293b', padding: 40, borderRadius: 20, alignItems: 'center', width: '80%' },
  unsupportedIcon: { fontSize: 64, marginBottom: 20 },
  unsupportedText: { color: '#fff', fontSize: 18, fontWeight: 'bold', textAlign: 'center' },
  unsupportedSub: { color: '#64748b', fontSize: 14, marginTop: 10, textAlign: 'center' },
  // Drawer Styles
  drawerContainer: { flex: 1, flexDirection: 'row' },
  drawerOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)' },
  drawerContent: { width: 280, height: '100%', backgroundColor: '#1e293b', padding: 25, paddingTop: 60 },
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
  
  uploadMenu: { position: 'absolute', bottom: 70, right: 0, backgroundColor: '#1e293b', borderRadius: 12, padding: 8, borderWidth: 1, borderColor: '#334155', elevation: 5, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.25, shadowRadius: 3.84, minWidth: 160 },
  uploadMenuItem: { flexDirection: 'row', alignItems: 'center', padding: 12, gap: 10 },
  uploadMenuText: { color: '#fff', fontSize: 14, fontWeight: '500' },
});
