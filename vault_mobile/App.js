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
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Video, ResizeMode } from 'expo-av';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { ActivityIndicator } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import * as api from './api';

const { width } = Dimensions.get('window');
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
  const [uploading, setUploading] = useState(false);
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

  useEffect(() => {
    checkConnection();
  }, []);

  const checkConnection = async () => {
    const conn = await api.getConnection();
    if (conn.token && conn.url) {
      setConnected(true);
      await loadData();
    } else {
        setLoading(false);
    }
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const me = await api.getMe();
      setRole(me.role);
      if (me.role !== 'admin' && me.allowed_folders.length > 0) {
          setCurrentFolder(me.allowed_folders[0]);
      }

      const [itemsList, sysStatus] = await Promise.all([
        api.fetchItems(),
        api.fetchStatus()
      ]);
      
      // Deduplicate items by ID (keep latest)
      const uniqueMap = new Map();
      itemsList.forEach(item => {
        uniqueMap.set(item.id, item);
      });
      
      setItems(Array.from(uniqueMap.values()));
      setStatus(sysStatus);
      setError('');
    } catch (e) {
      console.error(e);
      // If unauthorized, reset
      if (e.response?.status === 401) {
        handleLogout();
      } else {
        setError('Error de conexión o token revocado.');
      }
    } finally {
      setLoading(false);
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

  const handleCreateFolder = () => {
      if (!newFolderName.trim()) return;
      setCurrentFolder(newFolderName.trim());
      setNewFolderName('');
      setNewFolderModal(false);
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

  const handleUpload = async (type) => {
    let result;
    if (type === 'image') {
      result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.All,
        allowsEditing: false,
        quality: 1,
      });
    } else {
      result = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true });
    }

    if (!result.canceled) {
      setUploading(true);
      try {
          const asset = result.assets[0];
          const filename = asset.name || asset.fileName || asset.uri.split('/').pop() || 'upload.bin';
          await api.uploadFile(asset.uri, filename, asset.mimeType || 'application/octet-stream', currentFolder);
          alert('¡Archivo subido correctamente!');
          loadData();
      } catch(e) {
          alert('Error al subir: ' + e.message);
      }
      setUploading(false);
    }
  };

  const openPreview = async (item) => {
    setPreviewSrc(null); // Reset
    setPreviewItem(item);
    try {
        const src = await api.getMediaUrl(item);
        setPreviewSrc(src);
    } catch (e) {
        Alert.alert("Error", "No se pudo obtener la URL del archivo");
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
          const data = await api.createInvite(currentFolder);
          setInviteData(data);
          setInviteModal(true);
      } catch (e) {
          alert('Error creando invitación: ' + e.message);
      } finally {
          setLoading(false);
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
        <View>
            <Text style={styles.headerTitle}>Vault ({role === 'admin' ? 'Admin' : 'Estándar'})</Text>
            <Text style={styles.headerSub}>IP: {(url || '').replace('http://', '').split(':')[0] || '...'}</Text>

        </View>
        <TouchableOpacity onPress={loadData} disabled={loading}>
           {loading ? <ActivityIndicator color="#3b82f6"/> : <Text style={styles.headerAction}>Actualizar</Text>}
        </TouchableOpacity>
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
                            <Text style={[styles.folderChipText, currentFolder === f && styles.folderChipTextActive]}>
                                {f === 'root' ? '📅 Línea de Tiempo' : `📁 ${f}`}
                            </Text>
                        </TouchableOpacity>
                    )}
                />
                {role === 'admin' && (
                    <TouchableOpacity style={styles.addFolderBtn} onPress={() => setNewFolderModal(true)}>
                        <Text style={styles.addFolderText}>＋</Text>
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
                        <Text style={styles.deleteFolderText}>🗑️ Eliminar Carpeta</Text>
                    </TouchableOpacity>
                </View>
            )}
        </View>
      )}

      {/* Tabs */}
      <View style={styles.tabs}>
        <TouchableOpacity style={[styles.tab, view === 'gallery' && styles.tabActive]} onPress={() => setView('gallery')}>
          <Text style={[styles.tabText, view === 'gallery' && styles.tabTextActive]}>Archivos</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.tab, view === 'stats' && styles.tabActive]} onPress={() => setView('stats')}>
          <Text style={[styles.tabText, view === 'stats' && styles.tabTextActive]}>Panel Control</Text>
        </TouchableOpacity>
      </View>

      {/* Main View */}
      {view === 'gallery' ? (
        <View style={{ flex: 1 }}>
            {role === 'admin' && (
                <View style={styles.adminBar}>
                    <TouchableOpacity style={styles.inviteButtonFull} onPress={handleCreateInvite}>
                        <Text style={styles.inviteText}>Generar Acceso P2P a "{currentFolder === 'root' ? 'Línea de Tiempo' : currentFolder}"</Text>
                    </TouchableOpacity>
                </View>
            )}

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
            />

            {/* Subida Flotante */}
            <View style={styles.fabContainer}>
                {uploading ? (
                    <View style={styles.fab}><ActivityIndicator color="#fff"/></View>
                ) : (
                    <>
                    <TouchableOpacity style={[styles.fab, {marginBottom:10, backgroundColor: '#8b5cf6'}]} onPress={() => handleUpload('document')}>
                        <Text style={styles.fabIcon}>📄</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.fab} onPress={() => handleUpload('image')}>
                        <Text style={styles.fabIcon}>➕</Text>
                    </TouchableOpacity>
                    </>
                )}
            </View>
        </View>
      ) : (
        <View style={styles.statsContainer}>
          <View style={styles.statCard}>
             <Text style={styles.statLabel}>Espacio Libre en Disco</Text>
             <Text style={styles.statValue}>{Math.round(100 - (status?.disk?.percent || 0))}%</Text>
             <Text style={styles.statSub}>
                {formatBytes(status?.disk?.used || 0)} / {formatBytes(status?.disk?.total || 1)} ocupados
             </Text>
          </View>
          <View style={styles.statCard}>
             <Text style={styles.statLabel}>Memoria RAM</Text>
             <Text style={styles.statValue}>{Math.round(status?.ram?.percent || 0)}%</Text>
          </View>
          <View style={styles.statCard}>
             <Text style={styles.statLabel}>Total Archivos</Text>
             <Text style={styles.statValue}>{status?.vault?.file_count || 0}</Text>
          </View>
          <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
             <Text style={styles.logoutText}>Desvincular Dispositivo y Salir</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Preview Modal */}
      {previewItem && previewSrc && (
          <Modal visible={true} transparent={true} animationType="fade">
              <View style={styles.modalBg}>
                  <TouchableOpacity style={styles.modalClose} onPress={() => setPreviewItem(null)}>
                      <Text style={styles.modalCloseText}>Cerrar</Text>
                  </TouchableOpacity>
                  
                  {/* File Preview Logic */}
                  {(() => {
                      const name = previewItem?.name || 'archivo';
                      const ext = name.split('.').pop().toLowerCase();
                      const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext);
                      const isVideo = ['mp4', 'mov', 'm4v', 'avi', 'mkv', 'webm'].includes(ext);
                      
                      if (isImage) {
                          return (
                              <View style={styles.modalImageContainer}>
                                  <Image 
                                      source={previewSrc} 
                                      style={styles.modalImage} 
                                      resizeMode="contain" 
                                      onLoadStart={() => setPreviewLoading(true)}
                                      onLoadEnd={() => setPreviewLoading(false)}
                                  />
                                  {previewLoading && <ActivityIndicator size="large" color="#3b82f6" style={styles.spinner} />}
                              </View>
                          );
                      } else if (isVideo) {
                          return (
                              <Video
                                  source={previewSrc}
                                  rate={1.0}
                                  volume={1.0}
                                  isMuted={false}
                                  resizeMode={ResizeMode.CONTAIN}
                                  shouldPlay
                                  useNativeControls
                                  style={styles.modalImage}
                              />
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
                      <TouchableOpacity style={styles.modalSmallBtn} onPress={handleDownload}>
                          <Text style={styles.buttonText}>📤 Descargar</Text>
                      </TouchableOpacity>
                      {role === 'admin' && (
                          <TouchableOpacity style={[styles.modalSmallBtn, {backgroundColor: '#ef4444'}]} onPress={handleDeleteItem}>
                               <Text style={styles.buttonText}>🗑️ Borrar</Text>
                          </TouchableOpacity>
                      )}
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
                      <TextInput 
                        style={styles.input} 
                        placeholder="Nombre de la carpeta" 
                        placeholderTextColor="#64748b"
                        value={newFolderName}
                        onChangeText={setNewFolderName}
                        autoFocus
                      />
                      <View style={{flexDirection:'row', gap: 10}}>
                          <TouchableOpacity style={[styles.button, {flex:1, backgroundColor:'#334155'}]} onPress={() => setNewFolderModal(false)}>
                              <Text style={styles.buttonText}>Cancelar</Text>
                          </TouchableOpacity>
                          <TouchableOpacity style={[styles.button, {flex:1}]} onPress={handleCreateFolder}>
                              <Text style={styles.buttonText}>Crear</Text>
                          </TouchableOpacity>
                      </View>
                  </View>
              </View>
          </Modal>
      )}

      {/* Invite Modal */}
      {inviteModal && inviteData && (
           <Modal visible={true} transparent={true} animationType="slide">
              <View style={styles.modalBg}>
                   <View style={styles.qrCard}>
                       <Text style={styles.qrTitle}>Invitación a {inviteData.folder}</Text>
                       <Text style={styles.qrText}>Dile a un amigo que escanee este código o introduzca manualmente la URL y el PIN en su aplicación Vault Ingestor.</Text>
                       <Text style={styles.qrPin}>PIN: {inviteData.pin}</Text>
                       <TouchableOpacity style={{marginTop:30, padding: 15, backgroundColor:'#1e293b', borderRadius:8}} onPress={() => setInviteModal(false)}>
                           <Text style={{color:'#fff', fontWeight:'bold'}}>Cerrar Invitación</Text>
                       </TouchableOpacity>
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
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20, borderBottomWidth: 1, borderBottomColor: '#1e293b' },
  headerTitle: { fontSize: 20, fontWeight: 'bold', color: '#fff' },
  headerSub: { fontSize: 12, color: '#64748b', marginTop: 2 },
  headerAction: { color: '#3b82f6', fontWeight: 'bold' },
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
  tabs: { flexDirection: 'row', padding: 10 },
  tab: { flex: 1, padding: 10, alignItems: 'center', borderRadius: 8 },
  tabActive: { backgroundColor: '#1e293b' },
  tabText: { color: '#64748b', fontWeight: '600' },
  tabTextActive: { color: '#fff' },
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
  adminBar: { padding: 10 },
  inviteButtonFull: { backgroundColor: '#10b981', padding: 12, borderRadius: 8, alignItems: 'center' },
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
  unsupportedSub: { color: '#64748b', fontSize: 14, marginTop: 10, textAlign: 'center' }
});
