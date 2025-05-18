const form = document.getElementById('chat-form') as HTMLFormElement;
const responseBox = document.getElementById('response-box') as HTMLDivElement;

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(form);
  const message = formData.get('message') as string;

  const res = await fetch('/chat', {
    method: 'POST',
    body: formData,
  });

  const data = await res.json();
  responseBox.innerText = data.response;
});
