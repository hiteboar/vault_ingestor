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
  Dimensions
} from 'react-native';
import * as api from './api';

const { width } = Dimensions.get('window');
const COLUMN_COUNT = 3;
const ITEM_WIDTH = width / COLUMN_COUNT - 10;

export default function App() {
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('gallery'); // 'gallery' or 'stats'
  
  // Linking state
  const [url, setUrl] = useState('');
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');

  // Data state
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState(null);

  useEffect(() => {
    checkConnection();
  }, []);

  const checkConnection = async () => {
    const conn = await api.getConnection();
    if (conn.token && conn.url) {
      setConnected(true);
      loadData();
    }
    setLoading(false);
  };

  const loadData = async () => {
    try {
      const [itemsList, sysStatus] = await Promise.all([
        api.fetchItems(),
        api.fetchStatus()
      ]);
      setItems(itemsList);
      setStatus(sysStatus);
    } catch (e) {
      console.error(e);
      // If unauthorized, reset
      if (e.response?.status === 401) {
        handleLogout();
      }
    }
  };

  const handleLink = async () => {
    setError('');
    setLoading(true);
    try {
      const token = await api.verifyPin(url, pin);
      await api.saveConnection(url, token);
      setConnected(true);
      loadData();
    } catch (e) {
      setError('Error al vincular. Verifica la URL y el PIN.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    await api.clearConnection();
    setConnected(false);
  };

  if (loading && !connected) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color="#3b82f6" />
      </View>
    );
  }

  if (!connected) {
    return (
      <SafeAreaView style={styles.container}>
        <StatusBar barStyle="light-content" />
        <View style={styles.content}>
          <Text style={styles.title}>Vincular Vault</Text>
          <Text style={styles.subtitle}>Introduce los datos que aparecen en el Dashboard de escritorio.</Text>
          
          <TextInput 
            style={styles.input}
            placeholder="URL del Servidor (ej. http://192.168.1.10:8000)"
            placeholderTextColor="#64748b"
            value={url}
            onChangeText={setUrl}
            autoCapitalize="none"
          />
          
          <TextInput 
            style={styles.inputPin}
            placeholder="PIN de 6 dígitos"
            placeholderTextColor="#64748b"
            value={pin}
            onChangeText={setPin}
            keyboardType="numeric"
            maxLength={6}
          />
          
          {error ? <Text style={styles.errorText}>{error}</Text> : null}

          <TouchableOpacity style={styles.button} onPress={handleLink}>
            <Text style={styles.buttonText}>Vincular Dispositivo</Text>
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
        <Text style={styles.headerTitle}>Vault Mobile</Text>
        <TouchableOpacity onPress={loadData}>
           <Text style={styles.headerAction}>Actualizar</Text>
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <View style={styles.tabs}>
        <TouchableOpacity 
          style={[styles.tab, view === 'gallery' && styles.tabActive]}
          onPress={() => setView('gallery')}
        >
          <Text style={[styles.tabText, view === 'gallery' && styles.tabTextActive]}>Galería</Text>
        </TouchableOpacity>
        <TouchableOpacity 
          style={[styles.tab, view === 'stats' && styles.tabActive]}
          onPress={() => setView('stats')}
        >
          <Text style={[styles.tabText, view === 'stats' && styles.tabTextActive]}>Estado</Text>
        </TouchableOpacity>
      </View>

      {/* Main View */}
      {view === 'gallery' ? (
        <FlatList 
          data={items}
          numColumns={COLUMN_COUNT}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.gallery}
          renderItem={({ item }) => (
            <View style={styles.imageContainer}>
               <Image 
                source={{ uri: `${url}/api/media/thumbnail/${item.id}` }} 
                style={styles.thumbnail}
                resizeMode="cover"
               />
            </View>
          )}
        />
      ) : (
        <View style={styles.statsContainer}>
          <View style={styles.statCard}>
             <Text style={styles.statLabel}>Disco Duro</Text>
             <Text style={styles.statValue}>{Math.round(status?.disk?.percent || 0)}%</Text>
          </View>
          <View style={styles.statCard}>
             <Text style={styles.statLabel}>CPU</Text>
             <Text style={styles.statValue}>{Math.round(status?.cpu?.percent || 0)}%</Text>
          </View>
           <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
            <Text style={styles.logoutText}>Desvincular Dispositivo</Text>
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f172a',
  },
  content: {
    padding: 30,
    justifyContent: 'center',
    flex: 1,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 16,
    color: '#94a3b8',
    marginBottom: 40,
  },
  input: {
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 15,
    color: '#fff',
    marginBottom: 15,
    borderWidth: 1,
    borderColor: '#334155',
  },
  inputPin: {
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 15,
    color: '#3b82f6',
    fontSize: 24,
    fontWeight: 'bold',
    textAlign: 'center',
    marginBottom: 25,
    borderWidth: 1,
    borderColor: '#3b82f6',
  },
  button: {
    backgroundColor: '#3b82f6',
    borderRadius: 12,
    padding: 18,
    alignItems: 'center',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  errorText: {
    color: '#ef4444',
    marginBottom: 15,
    textAlign: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#1e293b',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#fff',
  },
  headerAction: {
    color: '#3b82f6',
  },
  tabs: {
    flexDirection: 'row',
    padding: 10,
  },
  tab: {
    flex: 1,
    padding: 10,
    alignItems: 'center',
    borderRadius: 8,
  },
  tabActive: {
    backgroundColor: '#1e293b',
  },
  tabText: {
    color: '#64748b',
    fontWeight: '600',
  },
  tabTextActive: {
    color: '#fff',
  },
  gallery: {
    padding: 5,
  },
  imageContainer: {
    margin: 5,
    width: ITEM_WIDTH,
    height: ITEM_WIDTH,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: '#1e293b',
  },
  thumbnail: {
    width: '100%',
    height: '100%',
  },
  statsContainer: {
    padding: 20,
    gap: 15,
  },
  statCard: {
    backgroundColor: '#1e293b',
    padding: 20,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#334155',
  },
  statLabel: {
    color: '#94a3b8',
    fontSize: 14,
    textTransform: 'uppercase',
    fontWeight: 'bold',
    marginBottom: 5,
  },
  statValue: {
    color: '#fff',
    fontSize: 32,
    fontWeight: 'bold',
  },
  logoutButton: {
    marginTop: 40,
    padding: 20,
    alignItems: 'center',
  },
  logoutText: {
    color: '#ef4444',
    fontWeight: '600',
  }
});
