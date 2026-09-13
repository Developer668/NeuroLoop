// Start Next.js' standalone server with its static assets and local-only defaults.
import {existsSync,cpSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {loadEnvFile} from 'node:process';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const buildDir=process.env.NEUROLOOP_BUILD_DIR||'.next';
const standalone=resolve(root,buildDir,'standalone');
if(!existsSync(resolve(standalone,'server.js')))throw new Error('Production build is missing. Run npm run build first.');
const localEnv=resolve(root,'.env.local');
if(existsSync(localEnv))loadEnvFile(localEnv);
mkdirSync(resolve(standalone,buildDir),{recursive:true});
cpSync(resolve(root,buildDir,'static'),resolve(standalone,buildDir,'static'),{recursive:true});
if(existsSync(resolve(root,'public')))cpSync(resolve(root,'public'),resolve(standalone,'public'),{recursive:true});
process.env.PORT=process.env.PORT||'3010';
process.env.HOSTNAME=process.env.NEUROLOOP_WEB_HOST||'127.0.0.1';
process.env.NEXT_TELEMETRY_DISABLED='1';
process.chdir(standalone);
await import(pathToFileURL(resolve(standalone,'server.js')).href);
