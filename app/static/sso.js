(() => { var h = (n, t, r, c = ["concordium", "metamask", "regular"], p, d, w = "sso") => { let s = n ? new URL(n)?.origin : "https://api.aesirx.io/", l = c?.length ? c?.map(i => `&login[]=${i}`).join("") : "", a = p && d ? "&demo_user=" + p + "&demo_password=" + d : "", E = `${s}/index.php?option=authorize&api=oauth2&response_type=code&client_id=${t}&state=${w}${l}${a}`, g = window.open(E, "SSO", "status=1,height=750,width=650"), u = setInterval(async () => { g.closed && (clearInterval(u), window.sso_response && r(window.sso_response)) }, 1e3); window.addEventListener("message", i => { if (i.origin === s && i.data && i.data.walletResponse) { let e = new URLSearchParams(i.data.walletResponse), o = { profile: { lastVisitDate: "" } }; e.get("access_token") && Object.assign(o, { access_token: e.get("access_token") }), e.get("expires_in") && Object.assign(o, { expires_in: e.get("expires_in") }), e.get("refresh_token") && Object.assign(o, { refresh_token: e.get("refresh_token") }), e.get("scope") && Object.assign(o, { scope: e.get("scope") }), e.get("token_type") && Object.assign(o, { scope: e.get("token_type") }), e.get("jwt") && Object.assign(o, { jwt: e.get("jwt") }), o && typeof window < "u" && (window.sso_response = o, g.close()) } }, !1) }, _ = async (n, t, r, c) => { let p = n ? new URL(n)?.origin : "https://api.aesirx.io/", d, w = typeof window < "u" && window.location.search, s = new URLSearchParams(w); if (t && s.get("state") === t) if (s.get("code")) { let a = await (await fetch(p + `/index.php?option=token&api=oauth2${t === "noscopes" ? "&state=noscopes" : ""}`, { method: "POST", body: JSON.stringify({ grant_type: "authorization_code", code: s.get("code"), client_id: r, client_secret: c }), headers: m({ "Content-Type": "application/json" }, { ["x-tracker-cache"]: d }) })).json(); a && typeof window < "u" && (window.opener.sso_response = a, a?.error || window.close()) } else s.get("error") && typeof window < "u" && window.close() }, m = (n, t) => (Object.keys(t).forEach(r => { t[r] !== void 0 && (n[r] = t[r]) }), n); var y = async () => { window.handleSSO = async n => { h(window.aesirxEndpoint, window.aesirxClientID, n, window.aesirxAllowedLogins, window.demoUser, window.demoPassword) }, _(window.aesirxEndpoint, window.aesirxSSOState ? window.aesirxSSOState : "sso", window.aesirxClientID, window.aesirxClientSecret) }; typeof window < "u" && window.aesirxClientID && (window.aesirxSSO = y()); var A = y; })();
