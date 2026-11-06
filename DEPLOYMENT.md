# Hebrew Font Lab — public release

Target address: https://fonts.aravrit.com
DNS provider observed: Bluehost (ns1.bluehost.com / ns2.bluehost.com).
The public app has NOT yet been deployed. No DNS changes have been made.

## Deploy

1. Sign in to Render. Publish this directory's source in a Git repository accessible to that account, or build and push the Docker image to a supported registry.
2. Create a Web Service using Docker. Use the Dockerfile in this directory. The image reads PORT and binds to 0.0.0.0. Health check: /health. Review the chosen instance plan before any paid activation. Classroom concurrency and resource limits need testing on the selected host.
3. Verify the app using the actual *.onrender.com address that Render assigns.
4. In that service's Settings → Custom Domains, add fonts.aravrit.com.
5. In the DNS manager for aravrit.com at Bluehost, add a CNAME for the host `fonts` pointing to the ACTUAL service's onrender.com hostname. There is deliberately no guessed hostname here. Check existing `fonts` records before replacing anything.
6. Verify the domain in Render, wait for certificate issuance, and test HTTPS and a complete worksheet-to-TTF round trip.

## Project separation and saving

Project data lives in each browser and JSON project downloads. Requests are processed in server memory without saving photos or fonts to disk. Hosting access metadata can still be retained by the provider. The hosted interface tells users photos are sent to the server. Original sample photos, exported fonts, personal project files and comparison assets are excluded from this release.

Keep the main aravrit.com site and its records as they are. This release targets only fonts.aravrit.com.
