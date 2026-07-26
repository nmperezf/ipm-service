import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

export function seedDatabase() {
  const dbPath = path.join(process.cwd(), 'ipm_service.db');
  try {
    if (fs.existsSync(dbPath)) {
      fs.unlinkSync(dbPath);
      console.log('Existing database removed:', dbPath);
    }
  } catch (err) {
    console.warn('Could not remove DB file:', err);
  }

  console.log('Running seed_demo.py to populate test data...');
  execSync('python seed_demo.py', { stdio: 'inherit' });
}

export function runCommand(cmd: string) {
  execSync(cmd, { stdio: 'inherit' });
}
