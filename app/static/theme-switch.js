const switching = document.querySelector('.switcher');
const body = document.getElementById('body');

const concordiumSmallLogo = document.getElementById('concordium-small');
const mainLargeLogo = document.getElementById('logo-logo');
const smallLogoInElements = document.querySelector('.small-logo');
const smallLogo = document.querySelector('.small-logo-in');
const smallLogoMarketCap = document.querySelector('.small-logo.inside');
const smallLogoStream = document.querySelector('.stream');

const mainLargeLogoBlack = '/static/logo_black_bg.png';
const mainLargeLogoWhite = '/static/logo_white_bg.jpg';
const concordiumSmallBlack = '/static/concordium-small-black.png';
const concordiumSmallWhite = '/static/concordium-small-white.png';
const smallLogoBlack = '/static/small-logo-black.png';
const smallLogoWhite = '/static/small-logo-white.png';


const switchingTheme = function () {

    if (!switching.classList.contains('switcher-animation-dark')) {
        switching.classList.add('switcher-animation-dark');
        body.classList.add('dark-theme');
        concordiumSmallLogo.src = concordiumSmallWhite;
        mainLargeLogo.src = mainLargeLogoBlack;
        smallLogoInElements.src = smallLogoWhite;
        smallLogoMarketCap.src = smallLogoWhite;

    } else if (switching.classList.contains('switcher-animation-dark')) {
        switching.classList.remove('switcher-animation-dark');
        body.classList.remove('dark-theme');
        concordiumSmallLogo.src = concordiumSmallBlack;
        mainLargeLogo.src = mainLargeLogoWhite;
        smallLogoInElements.src = smallLogoBlack;
        smallLogoMarketCap.src = smallLogoBlack;
    }
    console.log(smallLogoStream);
};

switching.addEventListener('click', switchingTheme);
