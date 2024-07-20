document.addEventListener('DOMContentLoaded', (event) => {
    const htmlElement = document.documentElement;
    const switchElement = document.getElementById('darkModeSwitch');
    const body = document.getElementById('body');
    
    const smallLogoBlack = '/static/small-logo-black.png';
    const smallLogoWhite = '/static/small-logo-white.png';

    const site_logo_dark = '/static/logo_dark_bg.png';
    const site_logo_light = '/static/logo_white_bg.png';
    
    // Set the default theme to dark if no setting is found in local storage
    const currentTheme = localStorage.getItem('bsTheme') || 'dark';
    htmlElement.setAttribute('data-bs-theme', currentTheme);
    switchElement.checked = currentTheme === 'dark';
    
    switchElement.addEventListener('change', function () {
        if (this.checked) {
            htmlElement.setAttribute('data-bs-theme', 'dark');
            localStorage.setItem('bsTheme', 'dark');
            // body.classList.add('dark-theme');
            const smallLogoMarketCap = document.getElementById('marketcap_logo');
            const site_logo = document.getElementById('logo');
            site_logo.src = site_logo_dark;
            smallLogoMarketCap.src = smallLogoWhite;
        } else {
            htmlElement.setAttribute('data-bs-theme', 'light');
            localStorage.setItem('bsTheme', 'light');
            // body.classList.remove('dark-theme');
            const smallLogoMarketCap = document.getElementById('marketcap_logo');
            const site_logo = document.getElementById('logo');
            smallLogoMarketCap.src = smallLogoBlack;
            site_logo.src = site_logo_light;
        }
    });
});