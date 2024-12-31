{
  "name": "your-project-name",
  "version": "1.0.0",
  "scripts": {
    "start": "uvicorn main:app --host 0.0.0.0 --port 8080",
    "build": "echo 'No build step for FastAPI, but ensuring Angular devDependencies are present'",
    "test": "echo \"Error: no test specified\" && exit 1"
  },
  "dependencies": {
    "fastapi": "^0.92.0",
    "mangum": "^0.17.0",
    "uvicorn": "^0.20.0"
  },
  "devDependencies": {
    "@angular/cli": "^17.0.0",
    "@angular-devkit/build-angular": "^17.0.0",
    "typescript": "^5.0.0"
  }
}
