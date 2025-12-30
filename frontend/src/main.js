import { CONFIG } from './config';

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
  dailyUsageText: document.getElementById('daily-usage-text'),
  progressBar: document.getElementById('usage-progress-bar'),
  paidAllowanceText: document.getElementById('paid-allowance-text'),
  slider: document.getElementById('topup-slider'),
  displayStars: document.getElementById('display-stars'),
  displayGB: document.getElementById('display-gb'),
  btnPurchase: document.getElementById('btn-purchase-slider'),

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
    // Hide all contents
    this.stateLoading.classList.add('hidden');
    this.stateDisconnected.classList.add('hidden');
    this.stateConnected.classList.add('hidden');
    this.stateError.classList.add('hidden');

    // Toggle Logout Button visibility
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
      this.displayEmail.textContent = data?.google_email || 'Unknown Email';
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

    const FREE_LIMIT_BYTES = 100 * 1024 * 1024; // 100 MB
    const dailyBytes = usage?.daily?.bytes || 0;
    const paidAllowance = usage?.paid_allowance || 0;

    // Update Progress Bar
    const progressPercent = Math.min(100, (dailyBytes / FREE_LIMIT_BYTES) * 100);
    this.progressBar.style.width = `${progressPercent}%`;
    this.dailyUsageText.textContent = `${formatBytes(dailyBytes)} / 100 MB used`;

    if (paidAllowance > 0) {
      this.paidAllowanceText.style.display = 'inline';
      this.paidAllowanceText.textContent = `+ ${formatBytes(paidAllowance)} paid remaining`;
    } else {
      this.paidAllowanceText.style.display = 'none';
    }

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
// Helpers
function formatBytes(bytes, decimals = 2) { // Increased decimals for precision
  if (bytes === 0) return '0 B';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  // Handle case where bytes < 1024 (index 0)
  if (bytes < k) return bytes + ' ' + sizes[0];

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

async function authenticate(initData, googleCode) {
  UI.showState('loading');
  try {
    const data = await callBackend('/authenticate', {
      initData,
      googleAuth: googleCode ? { code: googleCode, redirect_uri: CONFIG.auth.redirectUri } : undefined
    });

    if (data.user && data.user.google_email) {
      UI.showState('connected', data.user);
    } else {
      UI.showState('disconnected');
    }
  } catch (e) {
    UI.showState('error', "Authentication Failed: " + e.message);
  }
}

async function callBackend(path, payload) {
  const baseUrl = CONFIG.auth.backend;
  const res = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Server error: ${res.status}`);
  return data;
}

async function logout() {
  if (!confirm('Are you sure you want to unlink your Google Drive?')) return;
  try {
    UI.showState('loading');
    const initData = window.Telegram?.WebApp?.initData;
    await callBackend('/disconnect', { initData });
    window.location.reload();
  } catch (err) {
    UI.showState('error', err.message);
  }
}

// Initialization
const tg = window.Telegram?.WebApp;
if (!tg || !tg.initDataUnsafe?.user) {
  document.body.innerHTML = '<div style="padding:20px">Please open in Telegram</div>';
} else {
  tg.ready();
  tg.expand();
  UI.initUser(tg.initDataUnsafe.user);
  UI.btnLogout.onclick = logout;

  // Slider Logic
  if (UI.slider) {
    const updateSliderUI = () => {
      const stars = parseInt(UI.slider.value);
      // Linear scale: 1 Star = 0.02 GB (20MB = 20 * 1024 * 1024 bytes)
      const bytes = stars * 20 * 1024 * 1024;
      const sizeText = formatBytes(bytes);

      UI.displayStars.textContent = stars;
      UI.displayGB.textContent = sizeText;
      UI.btnPurchase.textContent = `Top-up ${sizeText} for ${stars} Stars`;
    };

    UI.slider.oninput = updateSliderUI;
    updateSliderUI();

    UI.btnPurchase.onclick = async () => {
      const stars = parseInt(UI.slider.value);
      const gb = stars * 0.02;
      const gbText = (gb < 0.1 ? gb.toFixed(3) : gb.toFixed(2)) + ' GB';

      try {
        UI.btnPurchase.disabled = true;
        const originalText = UI.btnPurchase.textContent;
        UI.btnPurchase.textContent = 'Generating...';

        const res = await callBackend('/create-invoice', {
          initData: tg.initData,
          stars: stars,
          gb: parseFloat(gb.toFixed(4))
        });

        if (res.invoiceLink) {
          tg.openInvoice(res.invoiceLink, (status) => {
            if (status === 'paid') {
              tg.showAlert(`Success! Your allowance has been increased.`);
              authenticate(tg.initData);
            }
            UI.btnPurchase.disabled = false;
            // Restore dynamic text
            UI.btnPurchase.textContent = `Top-up ${gbText} for ${stars} Stars`;
          });
        }
      } catch (err) {
        tg.showAlert('Error: ' + err.message);
        UI.btnPurchase.disabled = false;
        // Restore dynamic text
        UI.btnPurchase.textContent = `Top-up ${gbText} for ${stars} Stars`;
      }
    };
  }

  const startParam = tg.initDataUnsafe.start_param;
  const googleCode = startParam ? decodeBase64Url(startParam) : null;
  authenticate(tg.initData, googleCode);
}
