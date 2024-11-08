document.documentElement.setAttribute('data-bs-theme', (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'))

document.addEventListener('DOMContentLoaded', (event) => {
    const htmlElement = document.documentElement;
    const switchElement = document.getElementById('darkModeSwitch');
    
    const smallLogoTextBlack = '/static/logos/small-logo-black.png';
    const smallLogoTextWhite = '/static/logos/small-logo-white.png';

    const site_logo_dark = '/static/logos/logo_dark_bg.png';
    const site_logo_light = '/static/logos/logo_light_bg.png';
    
    // Set the default theme to dark if no setting is found in local storage
    const currentTheme = localStorage.getItem('bsTheme') || 'dark';
    htmlElement.setAttribute('data-bs-theme', currentTheme);
    switchElement.checked = currentTheme === 'dark';
    
    const light_mode_icon_str = '<i class="bi bi-sun-fill"></i> Light';
    const dark_mode_icon_str = '<i class="bi-moon-stars-fill"></i> Dark';

    switchElement.addEventListener('click', function () {
        
        if (this.innerHTML == light_mode_icon_str) {
            localStorage.setItem('bsTheme', 'dark');
            this.innerHTML = dark_mode_icon_str;
            htmlElement.setAttribute('data-bs-theme', 'dark');
            const site_logo = document.getElementById('logo');
            site_logo.src = site_logo_dark;
            const theme = 'dark';
            
        } else {
            localStorage.setItem('bsTheme', 'light');
            this.innerHTML = light_mode_icon_str
            htmlElement.setAttribute('data-bs-theme', 'light');
            const site_logo = document.getElementById('logo');
            site_logo.src = site_logo_light;
            const theme = 'light';
        }
        // Picked up by HTMX to trigger a reload of plotly graphs
        document.body.dispatchEvent(new CustomEvent("switched-theme"));
    });

});