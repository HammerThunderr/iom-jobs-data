export function wireShare() {
  document.querySelectorAll<HTMLButtonElement>('[data-share]').forEach((b) =>
    b.addEventListener('click', async () => {
      const data = { title: document.title, url: location.href };
      try {
        if (navigator.share) return await navigator.share(data);
        await navigator.clipboard.writeText(location.href);
        const old = b.innerHTML;
        b.textContent = 'Link copied';
        setTimeout(() => (b.innerHTML = old), 1800);
      } catch {}
    }),
  );
}
