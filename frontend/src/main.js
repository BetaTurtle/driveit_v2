import { auth, db, CONFIG } from './firebase-config';
import { onAuthStateChanged, signInWithCustomToken, signOut } from 'firebase/auth';
import { doc, getDoc, setDoc, updateDoc, serverTimestamp, deleteField } from 'firebase/firestore';

// UI Controller
const UI = {
  header: document.getElementById('profile-header'),
  profileLeft: document.querySelector('.profile-left'),
  stateLoading: document.getElementById('state-loading'),
  stateDisconnected: document.getElementById('state-disconnected'),
  stateConnected: document.getElementById('state-connected'),
  stateError: document.getElementById('state-error'),
  errorMsg: document.getElementById('error-msg'),
  btnConnect: document.getElementById('btn-connect'),
  displayEmail: document.getElementById('display-email'),
  btnLogout: document.getElementById('btn-logout'),

  initUser(user) {
    // Render Profile Header
    let avatarHtml = `<div class="avatar">${user.first_name[0]}</div>`;
    if (user.photo_url) {
      avatarHtml = `<img src="${user.photo_url}" class="avatar" alt="Avatar">`;
    }

    this.profileLeft.innerHTML = `
            ${avatarHtml}
            <div class="user-details">
                <div class="user-name">${user.first_name} ${user.last_name || ''}</div>
                <div class="user-handle">${user.username ? '@' + user.username : ''}</div>
            </div>
        `;
  },

  showState(stateName, data = null) {
    // Hide all
    this.stateLoading.classList.add('hidden');
    this.stateDisconnected.classList.add('hidden');
    this.stateConnected.classList.add('hidden');
    this.stateError.classList.add('hidden');

    // Toggle Logout Button
    if (stateName === 'connected') {
      this.btnLogout.classList.remove('hidden');
    } else {
      this.btnLogout.classList.add('hidden');
    }

    if (stateName === 'loading') {
      this.stateLoading.classList.remove('hidden');
    } else if (stateName === 'disconnected') {
      this.stateDisconnected.classList.remove('hidden');
      this.btnConnect.href = buildAuthUrl();
      this.btnConnect.onclick = () => {
        window.Telegram.WebApp.openLink(buildAuthUrl());
        window.Telegram.WebApp.close();
      };
    } else if (stateName === 'connected') {
      this.stateConnected.classList.remove('hidden');
      this.displayEmail.textContent = data?.google_email || data?.email || 'Unknown Email';
      this.renderStats(data?.usage);
    } else if (stateName === 'error') {
      this.stateError.classList.remove('hidden');
      this.errorMsg.textContent = data || 'Unknown Error';
    }
  },

  renderStats(usage) {
    const container = document.getElementById('usage-stats-container');
    if (!container) return;

    // Always show container if we are connected, even if stats are 0
    container.style.display = 'block';

    if (!usage) {
      // Reset to 0
      document.getElementById('stat-total-files').textContent = '0';
      document.getElementById('stat-total-size').textContent = '0 B';
      document.getElementById('stat-breakdown').innerHTML = '<div class="stat-item" style="grid-column: span 2;">No files uploaded yet</div>';
      return;
    }

    document.getElementById('stat-total-files').textContent = (usage.total_files || 0).toLocaleString();
    document.getElementById('stat-total-size').textContent = formatBytes(usage.total_bytes || 0);

    const breakdownHtml = [];
    const types = ['photo', 'video', 'audio', 'sticker', 'voice', 'video_note', 'document'];
    const labels = {
      photo: 'Photos', video: 'Videos', audio: 'Audio', document: 'Docs',
      sticker: 'Stickers', voice: 'Voice', video_note: 'Video Notes'
    };

    if (usage.breakdown) {
      types.forEach(type => {
        const data = usage.breakdown[type];
        if (data && data.count > 0) {
          breakdownHtml.push(`
                    <div class="stat-item">
                        <span class="stat-label">${labels[type] || type}</span>
                        <div class="stat-value">${data.count}</div>
                        <div style="font-size: 10px; opacity: 0.7;">${formatBytes(data.bytes)}</div>
                    </div>
                `);
        }
      });
    }

    const breakdownEl = document.getElementById('stat-breakdown');
    if (breakdownHtml.length > 0) {
      breakdownEl.innerHTML = breakdownHtml.join('');
    } else {
      breakdownEl.innerHTML = '<div class="stat-item" style="grid-column: span 2;">No uploads yet</div>';
    }
  }
};

// Helpers
function formatBytes(bytes, decimals = 1) {
  if (!+bytes) return '0 B';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function decodeBase64Url(str) {
  try {
    const base64 = str.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - str.length % 4) % 4);
    return new TextDecoder().decode(Uint8Array.from(atob(base64), c => c.charCodeAt(0)));
  } catch (e) { return null; }
}

function buildAuthUrl() {
  const params = new URLSearchParams({
    client_id: CONFIG.auth.clientId,
    redirect_uri: CONFIG.auth.redirectUri,
    response_type: 'code',
    scope: 'https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/userinfo.email',
    include_granted_scopes: 'true',
    prompt: 'consent',
    access_type: 'offline',
    state: Math.random().toString(36).slice(2)
  });
  return `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
}

// ---------------------------------------------------------
// AUTHENTICATION LOGIC (Optimized)
// ---------------------------------------------------------
async function authenticate(initData, googleCode) {
  UI.showState('loading');

  // 1. Optimistic Backend Request
  const backendTask = performBackendRequest(initData, googleCode);

  // 2. Local Session Check
  const firebaseTask = new Promise(resolve => {
    const unsubscribe = onAuthStateChanged(auth, user => {
      unsubscribe();
      resolve(user);
    });
  });

  let isUiUpdated = false;
  let backendError = null;

  // Background Finalizer
  const completeSignIn = async (data) => {
    if (!data.customToken) return;
    try {
      await signInWithCustomToken(auth, data.customToken);
      const user = auth.currentUser;

      const tgUser = window.Telegram.WebApp.initDataUnsafe.user;
      const userData = {
        telegram_id: tgUser.id,
        last_login: serverTimestamp(),
        user: tgUser
      };

      if (data.google?.email) {
        userData.google_email = data.google.email;
        userData.credentials = {
          access_token: data.google.access_token,
          refresh_token: data.google.refresh_token,
          expires_in: data.google.expires_in,
          obtained_at: Date.now()
        };
      }

      // Update DB
      const userRef = doc(db, 'users', user.uid);
      await setDoc(userRef, userData, { merge: true });

      // Critical Fix: If UI is not updated yet, check DB now
      if (!isUiUpdated) {
        const docSnap = await getDoc(userRef);
        const email = docSnap.data()?.google_email;
        if (email) {
          if (!isUiUpdated) {
            isUiUpdated = true;
            UI.showState('connected', docSnap.data());
          }
        } else {
          if (!isUiUpdated) {
            isUiUpdated = true;
            UI.showState('disconnected');
          }
        }
      }
    } catch (e) {
      console.error("Background sign-in failed:", e);
      if (!isUiUpdated) {
        UI.showState('error', "Sign-in Failed: " + e.message);
      }
    }
  };

  // Handlers
  const handleLocal = async (user) => {
    const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (user && tgUser && user.uid === String(tgUser.id)) {
      // Check local DB/Cache for email
      if (!isUiUpdated) {
        try {
          const userRef = doc(db, 'users', user.uid);
          const docSnap = await getDoc(userRef);
          const email = docSnap.data()?.google_email;
          if (email) {
            console.log("Local session valid. Updating UI.");
            isUiUpdated = true;
            UI.showState('connected', docSnap.data());

            // Update last login in bg
            setDoc(userRef, {
              last_login: serverTimestamp(),
              user: tgUser
            }, { merge: true });

            return { source: 'local', success: true };
          }
        } catch (e) { console.warn("Local DB fetch failed", e); }
      }
    }
    return { source: 'local', success: false };
  };

  const handleNetwork = async (data) => {
    if (data.error) throw new Error(data.error);

    if (data.google?.email && !isUiUpdated) {
      console.log("Backend success. Updating UI.");
      isUiUpdated = true;
      UI.showState('connected', { email: data.google.email });
    }

    completeSignIn(data);
    return { source: 'network', success: true };
  };

  // Logic Flow
  if (googleCode) {
    try {
      const data = await backendTask;
      await handleNetwork(data);
    } catch (e) {
      UI.showState('error', e.message);
    }
    return;
  }

  const localRace = firebaseTask.then(handleLocal).then(res => {
    if (res.success) return res;
    throw new Error("Local failed");
  });

  const networkRace = backendTask.then(handleNetwork).catch(e => {
    backendError = e.message;
    throw e;
  });

  try {
    await Promise.any([localRace, networkRace]);
  } catch (aggregateError) {
    // Both Failed
    if (!isUiUpdated) {
      // Double check current user just in case
      const user = auth.currentUser;
      if (user) {
        // Fallback attempt to read db
        handleLocal(user).then(res => {
          if (!res.success) UI.showState('disconnected');
        });
      } else {
        UI.showState('disconnected');
      }
    }
  }
}

async function performBackendRequest(initData, googleCode) {
  const authPayload = {
    initData,
    googleAuth: googleCode ? { code: googleCode, redirect_uri: CONFIG.auth.redirectUri } : undefined
  };

  const res = await fetch(CONFIG.auth.backend, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(authPayload)
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Server error: ${res.status}`);
  return data;
}

async function logout() {
  if (!confirm('Are you sure you want to unlink your Google Drive?')) return;
  try {
    const user = auth.currentUser;
    UI.showState('loading');
    if (user) {
      const userRef = doc(db, 'users', user.uid);
      await updateDoc(userRef, {
        google_email: deleteField(),
        credentials: deleteField()
      });
      await signOut(auth);
      window.location.reload();
    }
  } catch (err) {
    UI.showState('error', err.message);
  }
}

// Initialization
const tg = window.Telegram?.WebApp;
if (!tg || !tg.initDataUnsafe?.user) {
  // Browser Dev Mode Fallback
  document.body.innerHTML = '<div style="padding:20px">Please open in Telegram</div>';
} else {
  tg.ready();
  tg.expand();
  UI.initUser(tg.initDataUnsafe.user);
  UI.btnLogout.onclick = logout;

  const startParam = tg.initDataUnsafe.start_param;
  const googleCode = startParam ? decodeBase64Url(startParam) : null;
  authenticate(tg.initData, googleCode);
}
