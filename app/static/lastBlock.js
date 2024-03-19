  console.log("base_url=", base_url);
  
  function fadein(ele, value, updated) {
    if (updated) {
      delay = 500;
    } else {
      delay = 0;
    } 
    ele.classList.add('hide');
    setTimeout(function() { 
        ele.innerText = value;
        
    }, delay);
    setTimeout(function() { 
        ele.classList.remove('hide')
    }, delay);
  }
  
  function getState() {
    url = base_url+'/state/'+api_key+'/'+Math.floor(Date.now() / 1000);

    fetch(url)
      .then((response) => {
        return response.json();
        
      })
      .then((data) => {
        // console.log('DATA: ', data)
        var element_names = [
          'today_count_at', 'day_count_at', 'week_count_at', 'month_count_at', 'all_count_at',
          'today_tps', 'day_tps', 'week_tps', 'month_tps', 'all_tps', 
          'today_f_at', 'day_f_at', 'week_f_at', 'month_f_at'
        ];

        for (var i = 0; i < element_names.length; i++) {
          ele = document.getElementById(element_names[i]);
          if (ele.innerText != data.response[element_names[i]]) {
            // console.log('***', element_names[i],'|', ele.innerText, 'vs ', data.response[element_names[i]])
            fadein(ele, data.response[element_names[i]], data.updated);
          }
        }

      })
      .catch(function(error) {
        console.log(error);
      });

    
  }



  function startStream() {
    console.log('startStream...');
    url = base_url+'/stream-new-block';

    fetch(url)
      .then((response) => {
        console.log('startStream...request done.');
        return response.json();
        
      })
      .then((data) => {
        console.log('Message received:' + data);
      })
    }

  window.addEventListener('load', (event) => {
    // getState();
    // startStream();
    console.log('page is fully loaded');

  });
   
  // setInterval(getState, 11000);
