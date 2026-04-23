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
  Alert
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

const { width, height } = Dimensions.get('window');
const COLUMN_COUNT = 3;
const ITEM_WIDTH = width / COLUMN_COUNT - 10;

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
  
  // Modals state
  const [uploadState, setUploadState] = useState({ active: false, current: 0, total: 0, percent: 0 });
  const [previewItem, setPreviewItem] = useState(null);
  const [previewSrc, setPreviewSrc] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const [inviteModal, setInviteModal] = useState(false);
  const [inviteData, setInviteData] = useState(null);
  const [newFolderModal, setNewFolderModal] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  
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

      const [itemsList, sysStatus] = await Promise.all([
        api.fetchItems(),
        api.fetchStatus()
      ]);
      
      const uniqueMap = new Map();
      itemsList.forEach(item => {
        uniqueMap.set(item.id, item);
      });
      
      setItems(Array.from(uniqueMap.values()));
      setStatus(sysStatus);
      setLastUpdated(new Date());
      setError('');
    } catch (e) {
      if (e.response?.status === 401) {
        handleLogout();
      } else {
        setError('Error de conexión o token revocado.');
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
      setError('Error al vincular. Verifica la URL y el PIN o los permisos.');
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
         setError('Necesitas otorgar permiso de cámara para escanear.');
         return;
      }
    }
    setScanned(false);
    setShowScanner(true);
  };

  const handleDeleteItem = async () => {
    if (!previewItem) return;
    
    Alert.alert(
        'Eliminar Archivo',
        '¿Estás seguro de que quieres eliminar este archivo permanentemente?',
        [
            { text: 'Cancelar', style: 'cancel' },
            { 
                text: 'Eliminar', 
                style: 'destructive',
                onPress: async () => {
                    try {
                        setLoading(true);
                        await api.deleteItem(previewItem.id);
                        setPreviewItem(null);
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

  const handleDeleteFolder = async () => {
      if (currentFolder === 'root') return;
      
      Alert.alert(
          'Eliminar Carpeta',
          `¿Estás seguro de que quieres eliminar la carpeta "${currentFolder}" y TODOS sus archivos físicos?`,
          [
              { text: 'Cancelar', style: 'cancel' },
              { 
                  text: 'Borrar Todo', 
                  style: 'destructive',
                  onPress: async () => {
                        try {
                            setLoading(true);
                            await api.deleteFolder(currentFolder);
                            setCurrentFolder('root');
                            await loadData();
                        } catch (e) {
                            alert('Error al eliminar carpeta: ' + e.message);
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
          alert('Error al crear carpeta: ' + e.message);
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

  const handleUpload = async () => {
    const result = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, multiple: true });

    if (!result.canceled && result.assets && result.assets.length > 0) {
      const assets = result.assets;
      setUploadState({ active: true, current: 0, total: assets.length, percent: 0 });
      
      let successCount = 0;
      for (let i = 0; i < assets.length; i++) {
          const asset = assets[i];
          const filename = asset.name || asset.fileName || asset.uri.split('/').pop() || 'upload.bin';
          setUploadState(prev => ({ ...prev, current: i + 1, percent: 0 }));
          
          try {
              await api.uploadFile(asset.uri, filename, asset.mimeType || 'application/octet-stream', currentFolder, (pct) => {
                  setUploadState(prev => ({ ...prev, percent: pct }));
              });
              successCount++;
          } catch(e) {
              alert(`Error al subir ${filename}: ${e.message}`);
          }
      }
      
      setUploadState({ active: false, current: 0, total: 0, percent: 0 });
      loadData();
      if (successCount > 0 && successCount < assets.length) {
          alert(`Se subieron ${successCount} de ${assets.length} archivos correctamente.`);
      }
    }
  };

  const openPreview = async (item) => {
    setPreviewItem(item);
    setPreviewSrc(null);
    setPreviewLoading(true);
    setPreviewError(null);
    try {
        const src = await api.getMediaUrl(item);
        setPreviewSrc(src);
    } catch (e) {
        setPreviewError("No se pudo obtener la URL del archivo");
    }
  };

  const handleDownload = async () => {
    if(!previewItem || !previewSrc) return;
    try {
        const fileUri = FileSystem.cacheDirectory + previewItem.name;
        const downloadRes = await FileSystem.downloadAsync(previewSrc.uri, fileUri, { headers: previewSrc.headers });
        await Sharing.shareAsync(downloadRes.uri);
    } catch (e) {
        alert('Error al descargar: ' + e.message);
    }
  };

  const handleCreateInvite = async () => {
      try {
          setLoading(true);
          const data = await api.createInvite(selectedInviteFolders);
          setInviteData(data);
          setInviteModal(true);
          setInviteConfigModal(false);
          setDrawerOpen(false);
      } catch (e) {
          alert('Error creando invitación: ' + e.message);
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

  const renderThumbnail = ({ item }) => {
      // Usar useState hook interno para source es complejo. Lo ideal es montar un componente, pero como getThumbUrl 
      // devuelve un URI condicionado por promesas, vamos a construir la source aquí apoyándonos en que 
      // lo resolvimos parcialmente, o mejor aún, construimos la URI directamente si ya conocemos la url base.
      // Para evitar renders asíncronos lentos, pre-procesaremos las items en el futuro. Por ahora usamos useEffect.
      return <Thumbnail item={item} onPress={() => openPreview(item)} />;
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
                 <Text style={styles.buttonText}>Cancelar Escaneo</Text>
               </TouchableOpacity>
            </View>
          </SafeAreaView>
        );
      }
  
      return (
        <SafeAreaView style={styles.container}>
          <StatusBar barStyle="light-content" />
          <View style={styles.content}>
            <Text style={styles.title}>Vincular Vault</Text>
            <Text style={styles.subtitle}>Escanea un QR para entrar.</Text>
            
            <TouchableOpacity style={styles.buttonScan} onPress={openScanner}>
              <Text style={styles.buttonText}>📷 Escanear Código QR</Text>
            </TouchableOpacity>
  
            <View style={styles.divider}><Text style={styles.dividerText}>O MANUALMENTE</Text></View>
  
            <TextInput style={styles.input} placeholder="URL del Servidor" placeholderTextColor="#64748b" value={url} onChangeText={setUrl} autoCapitalize="none"/>
            <TextInput style={styles.inputPin} placeholder="PIN" placeholderTextColor="#3b82f6" value={pin} onChangeText={setPin} keyboardType="numeric" maxLength={6}/>
            
            {error ? <Text style={styles.errorText}>{error}</Text> : null}
  
            <TouchableOpacity style={[styles.button, (!url || !pin) && styles.buttonDisabled]} onPress={handleLink} disabled={!url || !pin}>
              <Text style={styles.buttonText}>Vincular</Text>
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
            <Text style={styles.headerTitle}>{view === 'stats' ? 'Panel de Control' : 'Vault Ingestor'}</Text>
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
                                {f === 'root' ? 'Línea de Tiempo' : f}
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
                    <Text style={styles.filterLabel}>Filtrar:</Text>
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

            {/* Folder Actions (Delete) */}
            {currentFolder !== 'root' && role === 'admin' && (
                <View style={styles.folderActions}>
                    <Text style={styles.folderPathText}>Gestionando: {currentFolder}</Text>
                    <TouchableOpacity onPress={handleDeleteFolder} style={styles.deleteFolderBtn}>
                        <MaterialCommunityIcons name="trash-can-outline" size={18} color="#ef4444" />
                        <Text style={styles.deleteFolderText}> Eliminar Carpeta</Text>
                    </TouchableOpacity>
                </View>
            )}
        </View>
      )}


      {/* Main View */}
      {view === 'gallery' ? (
        <View style={{ flex: 1 }}>

            <FlatList 
            data={items.filter(i => {
                // Folder logic:
                // 1. If searching for root, show everything with context root (date-organized)
                if (currentFolder === 'root') {
                    if (i.context !== 'root') return false;
                    // Apply year filter
                    if (selectedYear !== 'All') {
                        if (!i.timestamp.startsWith(selectedYear)) return false;
                    }
                    return true;
                }
                // 2. Otherwise, match by context (named folder)
                return i.context === currentFolder;
            })}
            numColumns={COLUMN_COUNT}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.gallery}
            renderItem={renderThumbnail}
            ListEmptyComponent={<Text style={{color:'#64748b', textAlign:'center', marginTop: 50}}>No hay archivos en esta carpeta</Text>}
            // OPTIMIZACIONES DE RENDIMIENTO
            windowSize={7} // Renderiza 3 pantallas arriba/abajo del viewport
            maxToRenderPerBatch={10} // Controla cuántos items se renderizan por lote
            updateCellsBatchingPeriod={50} // Tiempo entre lotes en ms
            initialNumToRender={12} // Renderiza 4 filas inmediatamente al inicio
            removeClippedSubviews={true} // Mejora memoria en Android al ocultar vistas fuera de pantalla
            />

            {/* Barra de progreso estática e inferior */}
            {uploadState.active && (
                <View style={{ position: 'absolute', bottom: 85, left: 15, right: 15, backgroundColor: '#1e293b', padding: 15, borderRadius: 12, borderWidth: 1, borderColor: '#334155', elevation: 5, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.25, shadowRadius: 3.84 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
                        <Text style={{ color: '#fff', fontSize: 14, fontWeight: 'bold' }}>
                            Subiendo archivo {uploadState.current} de {uploadState.total}...
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
                {uploadState.active ? (
                    <View style={styles.fab}><ActivityIndicator color="#fff"/></View>
                ) : (
                    <TouchableOpacity style={styles.fab} onPress={handleUpload}>
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
                <Text style={styles.statLabel}>Uso de Disco</Text>
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
                <Text style={styles.statLabel}>Uso de RAM</Text>
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
                <Text style={styles.statLabel}>Archivos en Bóveda</Text>
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
              <View style={styles.modalBg}>
                  <TouchableOpacity style={styles.modalClose} onPress={() => setPreviewItem(null)}>
                      <Text style={styles.modalCloseText}>Cerrar</Text>
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
                                              setPreviewError("Error al cargar la imagen");
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
                                              setPreviewError("Error al cargar el video");
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
                                  <Text style={styles.unsupportedSub}>Descarga el archivo para ver su contenido.</Text>
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
                      {role === 'admin' && (
                          <TouchableOpacity style={[styles.modalActionCircle, {backgroundColor: '#ef4444'}]} onPress={handleDeleteItem}>
                               <MaterialCommunityIcons name="trash-can-outline" size={24} color="#fff" />
                          </TouchableOpacity>
                      )}
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
                           <Text style={styles.drawerTitle}>Menú</Text>
                           <TouchableOpacity onPress={() => setDrawerOpen(false)}>
                               <Text style={{color:'#64748b', fontSize: 20}}>✕</Text>
                           </TouchableOpacity>
                       </View>

                       <View style={styles.drawerUserInfo}>
                           <Text style={styles.drawerRoleLabel}>Usuario</Text>
                           <Text style={styles.drawerRoleValue}>{role === 'admin' ? 'Administrador' : 'Estándar'}</Text>
                       </View>

                       <View style={styles.drawerDivider} />

                       <TouchableOpacity 
                           style={styles.drawerItem} 
                           onPress={() => { setView('stats'); setDrawerOpen(false); }}
                       >
                           <MaterialCommunityIcons name="monitor-dashboard" size={24} color="#3b82f6" style={styles.drawerItemIcon} />
                           <Text style={styles.drawerItemText}>Panel de Control</Text>
                       </TouchableOpacity>

                       {role === 'admin' && (
                           <TouchableOpacity 
                               style={styles.drawerItem} 
                               onPress={() => { setInviteConfigModal(true); setDrawerOpen(false); }}
                           >
                               <MaterialCommunityIcons name="account-plus-outline" size={24} color="#10b981" style={styles.drawerItemIcon} />
                               <Text style={styles.drawerItemText}>Invitar Usuario</Text>
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
                       <Text style={styles.promptTitle}>Configurar Invitación</Text>
                       <Text style={styles.promptSub}>Selecciona las carpetas a las que tendrá acceso el invitado:</Text>
                       
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
                                           {f === 'root' ? 'Línea de Tiempo (Todo)' : f}
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
                               <Text style={styles.buttonText}>Generar QR</Text>
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
                        <Text style={[styles.qrTitle, { fontSize: 24, marginBottom: 10, color: '#f8fafc' }]}>Invitación Creada</Text>
                        <Text style={[styles.qrText, { textAlign: 'center', color: '#94a3b8', marginBottom: 20, fontSize: 14 }]}>
                            El invitado debe escanear este código o introducir los datos manualmente.
                        </Text>
                        
                        <View style={{ backgroundColor: '#fff', padding: 10, borderRadius: 12, marginBottom: 20 }}>
                            <Image 
                                source={{ uri: `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(JSON.stringify({url: inviteData.url, pin: inviteData.pin}))}` }} 
                                style={{ width: 180, height: 180 }} 
                                resizeMode="contain"
                            />
                        </View>

                        <View style={{ width: '100%', backgroundColor: '#1e293b', padding: 15, borderRadius: 12, marginBottom: 20, borderColor: '#334155', borderWidth: 1 }}>
                            <Text style={{ color: '#64748b', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 5 }}>URL del Servidor</Text>
                            <Text style={{ color: '#60a5fa', fontSize: 16, fontWeight: '500', marginBottom: 15, textAlign: 'center' }} numberOfLines={2} adjustsFontSizeToFit>
                                {inviteData.url}
                            </Text>

                            <Text style={{ color: '#64748b', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 5 }}>PIN de Acceso</Text>
                            <Text style={{ color: '#10b981', fontSize: 32, fontWeight: 'bold', letterSpacing: 4, textAlign: 'center' }}>
                                {inviteData.pin}
                            </Text>
                        </View>

                        <TouchableOpacity style={{ width: '100%', padding: 16, backgroundColor: '#3b82f6', borderRadius: 8, alignItems: 'center' }} onPress={() => setInviteModal(false)}>
                            <Text style={{color:'#fff', fontWeight:'bold', fontSize: 16}}>Aceptar</Text>
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
                        <Text style={styles.promptTitle}>Nueva Carpeta</Text>
                        <Text style={styles.promptSub}>Introduce el nombre de la nueva carpeta para organizar tus archivos.</Text>
                        
                        <TextInput 
                            style={[styles.input, {marginVertical: 20, width: '100%'}]} 
                            placeholder="Nombre de la carpeta" 
                            placeholderTextColor="#64748b" 
                            value={newFolderName} 
                            onChangeText={setNewFolderName} 
                            autoCapitalize="none"
                            autoFocus={true}
                        />

                        <View style={{flexDirection:'row', gap: 10}}>
                            <TouchableOpacity style={[styles.button, {flex:1, backgroundColor:'#334155'}]} onPress={() => {setNewFolderModal(false); setNewFolderName('');}}>
                                <Text style={styles.buttonText}>Cancelar</Text>
                            </TouchableOpacity>
                            <TouchableOpacity 
                                style={[styles.button, {flex:1}, !newFolderName.trim() && styles.buttonDisabled]} 
                                onPress={handleCreateFolder}
                                disabled={!newFolderName.trim()}
                            >
                                <Text style={styles.buttonText}>Crear</Text>
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
function Thumbnail({ item, onPress }) {
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
            <TouchableOpacity style={styles.imageContainer} onPress={onPress}>
                <View style={styles.filePlaceholder}>
                    <Text style={styles.fileIcon}>{isVideo ? '🎬' : '📄'}</Text>
                    <Text style={styles.fileNameText} numberOfLines={2}>{item.name}</Text>
                </View>
            </TouchableOpacity>
        );
    }

    return (
        <TouchableOpacity style={styles.imageContainer} onPress={onPress}>
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
  gallery: { padding: 5, paddingBottom: 100 },
  imageContainer: { margin: 5, width: ITEM_WIDTH, height: ITEM_WIDTH, borderRadius: 8, overflow: 'hidden', backgroundColor: '#1e293b' },
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
  folderSelectItemTextActive: { color: '#fff', fontWeight: 'bold' }
});
