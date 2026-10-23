const fs = require('node:fs');
const path = require('node:path');

module.exports = async function runMediaSmoke(window, videoPath, reportPath, artifactDir) {
  const video = fs.readFileSync(videoPath).toString('base64');
  const report = fs.readFileSync(reportPath).toString('base64');
  const result = await window.webContents.executeJavaScript(`(async () => {
    function attach(index, name, mime, encoded) {
      const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
      const file = new File([bytes], name, {type: mime});
      const transfer = new DataTransfer(); transfer.items.add(file);
      const input = document.querySelectorAll('.media-evidence input[type=file]')[index];
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', {bubbles: true}));
    }
    attach(0, 'clip.webm', 'video/webm', ${JSON.stringify(video)});
    attach(1, 'report.json', 'application/json', ${JSON.stringify(report)});
    const until = Date.now() + 12000;
    while (Date.now() < until) {
      const text = document.querySelector('.media-evidence')?.textContent ?? '';
      const player = document.querySelector('.media-evidence video');
      const button = document.querySelector('.media-evidence li button');
      if (text.includes('与报告一致') && player?.readyState >= 1 && button && !button.disabled) {
        button.click();
        await new Promise(resolve => setTimeout(resolve, 100));
        return {hashVerified:true, videoReady:true, selectedTime:player.currentTime,
          frameWarning:text.includes('疑似缺帧'), eventLabel:button.textContent};
      }
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    const player = document.querySelector('.media-evidence video');
    throw new Error('Media view failed: ' + JSON.stringify({text:document.querySelector('.media-evidence')?.textContent,
      readyState:player?.readyState, networkState:player?.networkState, error:player?.error?.code,
      currentSrc:player?.currentSrc, canPlay:player?.canPlayType('video/webm')}));
  })()`);
  if (!result.hashVerified || !result.videoReady || Math.abs(result.selectedTime - 0.4) > 0.15 || !result.frameWarning) {
    throw new Error('Media evidence mismatch: ' + JSON.stringify(result));
  }
  fs.writeFileSync(path.join(artifactDir, 'media-view.png'), (await window.webContents.capturePage()).toPNG());
  console.log(JSON.stringify({event:'desktop_media_smoke', ...result}));
};
