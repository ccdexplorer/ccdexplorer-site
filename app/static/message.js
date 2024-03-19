function getMessage() {
  url = "https://raw.githubusercontent.com/sderuiter/concordium-messaging/main/home.json";
  fetch(url)
    .then((response) => {
      return response.json();
      
    })
    .then((data) => {
      ele = document.getElementById("message");
      if (data.message === "") {
        
      } else {
        ele.innerText = data.message;
        ele.classList.remove('hide');
        ele.classList.remove('hidden');
      }

    })
    .catch(function(error) {
      console.log(error);
    });

  
}

window.addEventListener('load', (event) => {
  getMessage();
});