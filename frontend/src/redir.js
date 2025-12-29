(function () {
    const status = document.getElementById('status');
    const error = document.getElementById('error');

    // Convert authorization code to Telegram-friendly format
    function toBase64Url(str) {
        try {
            const bytes = new TextEncoder().encode(str);
            const binary = Array.from(bytes)
                .map(byte => String.fromCharCode(byte))
                .join('');
            return btoa(binary)
                .replace(/\+/g, '-')
                .replace(/\//g, '_')
                .replace(/=+$/, '');
        } catch (e) {
            console.error('Encoding error:', e);
            return null;
        }
    }

    // Handle redirect
    function handleRedirect() {
        try {
            const params = new URLSearchParams(window.location.search);
            const code = params.get('code');

            if (!code) {
                throw new Error('No authorization code received');
            }

            const encoded = toBase64Url(code);
            if (!encoded) {
                throw new Error('Failed to encode authorization code');
            }

            const telegramUrl = 'https://t.me/DriveItBot/manage?startapp=' + encoded;
            window.location.replace(telegramUrl);

        } catch (e) {
            console.error('Redirect error:', e);
            status.style.display = 'none';
            if (error) {
                error.style.display = 'block';
                error.textContent = 'Failed to connect: ' + e.message;
            }
        }
    }

    // Start redirect process
    handleRedirect();
})();
