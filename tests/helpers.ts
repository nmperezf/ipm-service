import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

export function seedDatabase() {
  const dbPath = path.join(process.cwd(), 'ipm_service.db');
  const marker = path.join(process.cwd(), 'tests', '.seeded');

  // Try to create a marker file atomically so only one process runs the seeding.
  try {
    const fd = fs.openSync(marker, 'wx');
    fs.closeSync(fd);

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

    // mark as seeded
    try {
      fs.writeFileSync(marker, 'seeded');
    } catch (e) {
      console.warn('Could not write seed marker file:', e);
    }
  } catch (err: any) {
    // If marker exists, another process is seeding or seeding already done. Skip silently.
    if (err && (err.code === 'EEXIST' || err.code === 'EACCES')) {
      return;
    } else {
      console.warn('Unexpected error while attempting to create seed marker:', err);
    }
  }
}

export function runCommand(cmd: string) {
  execSync(cmd, { stdio: 'inherit' });
}
