(() => {
  const logoutLink = document.getElementById("logoutLink");
  const logoutForm = document.getElementById("logoutForm");

  if (!logoutLink || !logoutForm) return;

  logoutLink.addEventListener("click", (event) => {
    event.preventDefault();
    const ok = window.confirm("Voulez-vous vraiment vous déconnecter ?");
    if (!ok) return;
    logoutForm.submit();
  });
})();
