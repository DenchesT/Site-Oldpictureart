// Маленький веб-сервер для проверок: отдаёт папку docs по http://127.0.0.1.
//
// Страницы с file:// открываются и так, но запросы к файлам на диске
// Playwright перехватывать не умеет. А некоторым проверкам нужно как раз
// это — например, «библиотека группировки меток не загрузилась».
const http = require('http');
const fs = require('fs');
const path = require('path');

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'application/javascript',
  '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp',
  '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.ico': 'image/x-icon', '.xml': 'application/xml',
  '.ics': 'text/calendar', '.txt': 'text/plain; charset=utf-8',
};

function serve(root) {
  return new Promise(resolve => {
    const server = http.createServer((req, res) => {
      let rel = decodeURIComponent(new URL(req.url, 'http://x').pathname);
      if (rel.endsWith('/')) rel += 'index.html';
      const file = path.join(root, path.normalize(rel).replace(/^([/\\])+/, ''));
      if (!file.startsWith(path.resolve(root))) { res.writeHead(403); return res.end(); }
      fs.readFile(file, (err, body) => {
        if (err) { res.writeHead(404); return res.end(); }
        res.writeHead(200, { 'Content-Type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream' });
        res.end(body);
      });
    });
    server.listen(0, '127.0.0.1', () => resolve({
      url: `http://127.0.0.1:${server.address().port}`,
      close: () => new Promise(r => server.close(r)),
    }));
  });
}

module.exports = { serve };
