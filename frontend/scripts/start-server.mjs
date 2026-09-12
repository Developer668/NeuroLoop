// Start Next.js' standalone server with its static assets and local-only defaults.
import {existsSync,cpSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const standalone=resolve(root,'.next/standalone');
if(!existsSync(resolve(standalone,'server.js')))throw new Error('Production build is missing. Run npm run build first.');
mkdirSync(resolve(standalone,'.next'),{recursive:true});
cpSync(resolve(root,'.next/static'),resolve(standalone,'.next/static'),{recursive:true});
if(existsSync(resolve(root,'public')))cpSync(resolve(root,'public'),resolve(standalone,'public'),{recursive:true});
process.env.PORT=process.env.PORT||'3010';
process.env.HOSTNAME=process.env.NEUROLOOP_WEB_HOST||'127.0.0.1';
process.env.NEXT_TELEMETRY_DISABLED='1';
process.chdir(standalone);
await import(pathToFileURL(resolve(standalone,'server.js')).href);
