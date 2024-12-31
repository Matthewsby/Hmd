{
  "version": 2,
  "builds": [
    {
      "src": "path/to/your/app.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "path/to/your/app.py"
    }
  ]
}