
function fadein(ele, value, updated) {
  if (updated) {
    delay = 500;
  } else {
    delay = 0;
  }
  ele.classList.add('hide');
  setTimeout(function () {
    ele.innerText = value;

  }, delay);
  setTimeout(function () {
    ele.classList.remove('hide')
  }, delay);
}

function fadeinHTML(ele, value, updated) {
  if (updated) {
    delay = 500;
  } else {
    delay = 0;
  }
  ele.classList.add('hide');
  setTimeout(function () {
    ele.innerHTML = value;

  }, delay);
  setTimeout(function () {
    ele.classList.remove('hide')
  }, delay);
}

function updateAccounts(message) {
  // console.log(message)
  var element_names = [
    // 'newest-0', 'newest-1', 'newest-2', 'newest-3', 'newest-4', 'newest-5', 'newest-6', 'newest-7', 'newest-8', 'newest-9',
    // 'newest-0-since', 'newest-1-since', 'newest-2-since', 'newest-3-since', 'newest-4-since', 'newest-5-since', 'newest-6-since', 'newest-7-since', 'newest-8-since', 'newest-9-since',
    'largest-0', 'largest-1', 'largest-2', 'largest-3', 'largest-4', 'largest-5', 'largest-6', 'largest-7', 'largest-8', 'largest-9',
    'largest-0-amount', 'largest-1-amount', 'largest-2-amount', 'largest-3-amount', 'largest-4-amount', 'largest-5-amount', 'largest-6-amount', 'largest-7-amount', 'largest-8-amount', 'largest-9-amount',
    'most_active-0', 'most_active-1', 'most_active-2', 'most_active-3', 'most_active-4', 'most_active-5', 'most_active-6', 'most_active-7', 'most_active-8', 'most_active-9',
    'most_active-0-tx', 'most_active-1-tx', 'most_active-2-tx', 'most_active-3-tx', 'most_active-4-tx', 'most_active-5-tx', 'most_active-6-tx', 'most_active-7-tx', 'most_active-8-tx', 'most_active-9-tx'
  ];

  for (var i = 0; i < element_names.length; i++) {
    ele = document.getElementById(element_names[i]);
    if (ele !== null) {
      if (ele.innerHTML != message[element_names[i]]) {
        // console.log('***', element_names[i]);
        // console.log(ele.innerHTML);
        // console.log(message[element_names[i]]);
        // console.log('***', element_names[i]);
        fadeinHTML(ele, message[element_names[i]], message.updated);
      }
    }
  }

}

function updateState(message) {
  var element_names = [
    'hour_count_at', 'day_count_at', 'week_count_at', 'month_count_at', 'year_count_at',
    'hour_tps', 'day_tps', 'week_tps', 'month_tps', 'year_tps',
    'hour_f_at', 'day_f_at', 'week_f_at', 'month_f_at'
  ];

  for (var i = 0; i < element_names.length; i++) {
    ele = document.getElementById(element_names[i]);
    if (ele !== null) {
      if (ele.innerText != message[element_names[i]]) {
        //   console.log('***', element_names[i],'|', ele.innerText, 'vs ', message[element_names[i]])
        fadein(ele, message[element_names[i]], message.updated);
      }
    }
  }

}

function updateCNS(message) {
  var element_names = [
    // 'name_1', 'name_2', 'name_3', 'name_4', 'name_5'
    'names'
  ];

  for (var i = 0; i < element_names.length; i++) {
    ele = document.getElementById(element_names[i]);
    if (ele.innerText != message[element_names[i]]) {
      //   console.log('***', element_names[i],'|', ele.innerText, 'vs ', message[element_names[i]])
      fadeinHTML(ele, message[element_names[i]], message.updated);
    }
  }

}

function updateBlock(message) {
  // console.log('updateBlock')
  net = document.getElementById('meta_data_net').title;

  if (net == message.net) {
    document.getElementById('height').setAttribute('href', '/' + net + '/block/' + message['full_hash']);

    var element_names = [
      'height', 'consensus_fin_period_combined', 'consensus_tx_per_block_combined', 'ccd_outstanding'
    ];


    for (var i = 0; i < element_names.length; i++) {
      ele = document.getElementById(element_names[i]);
      if (ele.innerText != message[element_names[i]]) {
        //   console.log('***', element_names[i],'|', ele.innerText, 'vs ', message[element_names[i]])
        fadein(ele, message[element_names[i]], message.updated);
      }
    }
  }
}

window.addEventListener('load', (event) => {
  // console.log('page is fully loaded. On to the websocket!');
  let domain = (new URL(base_url));
  host = domain.host;//.replace('www.','');
  protocol = (domain.protocol == 'https:') ? 'wss:' : 'ws:'

  var ws = new ReconnectingWebSocket(protocol + "//" + host + "/ws");
  ws.onopen = function (event) {
    ws.send(JSON.stringify('True'))
  }
  ws.onmessage = function (event) {

    message = JSON.parse(event.data);
    // console.log("Message received: ", message)

    if (message.type == 'accounts_response') {
      updateAccounts(message);
    }

    if (message.type == 'state_response') {
      console.log("MESSAGE: ", message)
      updateState(message);
    }

    //   if (message.type == 'cns_response') {
    //     updateCNS(message);
    // }

    if (message.type == 'block_response') {
      updateBlock(message);
    }

  };
});