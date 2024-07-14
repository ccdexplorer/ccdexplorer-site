const switching = document.querySelector('.theme-switcher');
const body = document.getElementById('body');

const concordiumSmallLogo = document.getElementById('concordium-small');
const mainLargeLogo = document.getElementById('logo-lg');
const smallLogoInElements = document.querySelector('.logo-sm');
const smallLogo = document.querySelector('.logo-sm-in');
const smallLogoMarketCap = document.querySelector('.logo-sm.inside');
const smallLogoStream = document.querySelector('.stream');

const mainLargeLogoBlack = '/static/logo_black_bg.png';
const mainLargeLogoWhite = '/static/logo_white_bg.jpg';
const concordiumSmallBlack = '/static/concordium-small-black.png';
const concordiumSmallWhite = '/static/concordium-small-white.png';
const smallLogoBlack = '/static/small-logo-black.png';
const smallLogoWhite = '/static/small-logo-white.png';


const switchingTheme = function () {

    let theme = 'light';

    if (!switching.classList.contains('theme-switcher-animation-dark')) {
        switching.classList.add('theme-switcher-animation-dark');
        body.classList.add('dark-theme');
        concordiumSmallLogo.src = concordiumSmallWhite;
        mainLargeLogo.src = mainLargeLogoBlack;
        smallLogoInElements.src = smallLogoWhite;
        smallLogoMarketCap.src = smallLogoWhite;
        theme = 'dark';

    } else if (switching.classList.contains('theme-switcher-animation-dark')) {
        switching.classList.remove('theme-switcher-animation-dark');
        body.classList.remove('dark-theme');
        concordiumSmallLogo.src = concordiumSmallBlack;
        mainLargeLogo.src = mainLargeLogoWhite;
        smallLogoInElements.src = smallLogoBlack;
        smallLogoMarketCap.src = smallLogoBlack;
    }

    localStorage.setItem('theme', theme);
};


let theme;
if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    theme = 'dark';
}

theme = localStorage.getItem('theme') || theme;

if (theme == 'dark') {
    switchingTheme();
}

switching.addEventListener('click', switchingTheme);
