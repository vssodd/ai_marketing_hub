// Disable video on small screens
if (window.innerWidth < 768) {
  const vid = document.getElementById('bg-video');
  vid.parentNode.removeChild(vid);
  document.body.style.background = 'url(media/videos/fallback.jpg) center/cover no-repeat';
}
