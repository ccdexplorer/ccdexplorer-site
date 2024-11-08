/*!
 * Color mode toggler for Bootstrap's docs (https://getbootstrap.com/)
 * Copyright 2011-2024 The Bootstrap Authors
 * Licensed under the Creative Commons Attribution 3.0 Unported License.
 */

(() => {
    'use strict'
  
    const getStoredTheme = () => localStorage.getItem('theme')
    const setStoredTheme = theme => localStorage.setItem('theme', theme)
  
    const getPreferredTheme = () => {
      const storedTheme = getStoredTheme()
      if (storedTheme) {
        return storedTheme
      }
  
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
  
    const setTheme = theme => {
      if (theme === 'auto') {
        document.documentElement.setAttribute('data-bs-theme', (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'))
      } else {
        document.documentElement.setAttribute('data-bs-theme', theme)
      }
    
    }

    const flipLogos = theme => {
        if (theme === 'auto') {
          theme = (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        } else {
          document.documentElement.setAttribute('data-bs-theme', theme)
        }
        const small_logo_dark = '/static/logos/small-logo_dark.png';
        const small_logo_light = '/static/logos/small-logo_light.png';
  
        const site_logo_dark = '/static/logos/logo_dark.png';
        const site_logo_light = '/static/logos/logo_light.png';
        
        const light_mode_icon_str = '<i class="bi bi-sun-fill"></i> Light';
        const dark_mode_icon_str = '<i class="bi-moon-stars-fill"></i> Dark';

        const site_logo = document.getElementById('logo');
        const crypto_logo = document.getElementById('crypto_logo');
        if (theme === 'dark') {
            site_logo.src = site_logo_dark;
            crypto_logo.src = small_logo_dark;
        }

        if (theme === 'light') {
            site_logo.src = site_logo_light;
            crypto_logo.src = small_logo_light;
        }
      
      }

    const dispatchEventPlotly = theme => {
        // Picked up by HTMX to trigger a reload of plotly graphs
        document.body.dispatchEvent(new CustomEvent("switched-theme"));
      }

   
  
  
    setTheme(getPreferredTheme())
    
    const showActiveTheme = (theme, focus = false) => {
      const themeSwitcher = document.querySelector('#bd-theme')
  
      if (!themeSwitcher) {
        return
      }
      
       
  
      const themeSwitcherText = document.querySelector('#bd-theme-text')
      const activeThemeIcon = document.querySelector('.theme-icon-active use')
      const btnToActive = document.querySelector(`[data-bs-theme-value="${theme}"]`)
      const svgOfActiveBtn = btnToActive.querySelector('svg use').getAttribute('href')
  
      document.querySelectorAll('[data-bs-theme-value]').forEach(element => {
        element.classList.remove('active')
        element.setAttribute('aria-pressed', 'false')
      })
  
      btnToActive.classList.add('active')
      btnToActive.setAttribute('aria-pressed', 'true')
      activeThemeIcon.setAttribute('href', svgOfActiveBtn)
      const themeSwitcherLabel = `${themeSwitcherText.textContent} (${btnToActive.dataset.bsThemeValue})`
      themeSwitcher.setAttribute('aria-label', themeSwitcherLabel)
  
      if (focus) {
        themeSwitcher.focus()
      }
    }
  
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      const storedTheme = getStoredTheme()
      if (storedTheme !== 'light' && storedTheme !== 'dark') {
        setTheme(getPreferredTheme())
      }
    })
  
    window.addEventListener('DOMContentLoaded', () => {
      showActiveTheme(getPreferredTheme())
  
    
        
        
      document.querySelectorAll('[data-bs-theme-value]')
        .forEach(toggle => {
          toggle.addEventListener('click', () => {
            const theme = toggle.getAttribute('data-bs-theme-value')
            setStoredTheme(theme)
            setTheme(theme)
            showActiveTheme(theme, true)
            flipLogos(theme)  
            dispatchEventPlotly(theme)
          })
        })
    })
  })()
  