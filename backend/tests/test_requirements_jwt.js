const fs = require('fs');
const path = require('path');

const req = fs.readFileSync(path.resolve(__dirname, '..', 'requirements.txt'), 'utf8');

if (!req.includes('PyJWT')) {
  console.error('FAIL: backend requirements must declare PyJWT');
  process.exit(1);
}

console.log('backend requirements declare PyJWT');
