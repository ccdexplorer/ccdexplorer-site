document.addEventListener('input', function (event) {

	// Only run on our select menu
	if (event.target.id !== 'net_switcher') return;

	// The selected value
	const selected_net = event.target.value;
    if (selected_net == "mainnet") {
        window.location.href = '/mainnet';
    }

    if (selected_net == "testnet") {
        window.location.href = '/testnet';
    }
}, false);
