const CACHE='spritedex-v21-5-20260723';
const ASSETS=['./','./index.html','./sprites.json','./manifest.webmanifest','./icon-192.png','./icon-512.png'];

self.addEventListener('install',event=>{
 event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting()));
});

self.addEventListener('activate',event=>{
 event.waitUntil(
  caches.keys()
   .then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key))))
   .then(()=>self.clients.claim())
 );
});

self.addEventListener('fetch',event=>{
 const request=event.request;
 if(request.method!=='GET')return;

 const url=new URL(request.url);
 if(url.origin!==location.origin)return;

 if(url.pathname.endsWith('/sprites.json')){
  event.respondWith(
   caches.match(request).then(cached=>{
    const update=fetch(request).then(response=>{
     if(response.ok)caches.open(CACHE).then(cache=>cache.put(request,response.clone()));
     return response;
    }).catch(()=>cached);
    return cached||update;
   })
  );
  return;
 }

 event.respondWith(
  caches.match(request).then(cached=>cached||fetch(request).then(response=>{
   if(response.ok)caches.open(CACHE).then(cache=>cache.put(request,response.clone()));
   return response;
  }))
 );
});
