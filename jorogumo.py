#!/usr/bin/env python3.7

import asyncio
import logging
import re
import signal
import sys
import urllib.parse
import ssl
import time
import aiohttp


ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
sslcontext = ctx

timeout = aiohttp.ClientTimeout(total=20)

class Crawler:

    def __init__(self, rooturl, maxtasks=100):
        self.rooturl = rooturl
        self.todo = set()
        self.busy = set()
        self.done = {}
        self.tasks = set()
        self.sem = asyncio.Semaphore(maxtasks)
        self.file = open(urllib.parse.urlparse(rooturl).netloc + "-" + str(int(time.time())), "w+")
        # connector stores cookies between requests and uses connection pool
        self.session = aiohttp.ClientSession(timeout=timeout)

    async def writeToFile(self, string):
        self.file.write(string + "\n")
        return

    async def run(self):
        t = asyncio.ensure_future(self.addurls([(self.rooturl, '')]))
        await asyncio.sleep(1)
        while self.busy:
            await asyncio.sleep(1)

        await t
        await self.session.close()

    async def checkRecursion(self, url):
        folders = url.split("/")
        ufolders = set(folders)
        for i in ufolders:
            if folders.count(i) > 2:
                return True
        return False

    async def addurls(self, urls):
        for url, parenturl in urls:
            url = urllib.parse.urljoin(parenturl, url)
            url, frag = urllib.parse.urldefrag(url)
            urlnetloc = urllib.parse.urlparse(url).netloc
            if (url.startswith(self.rooturl) and
                    url not in self.busy and
                    url not in self.done and
                    url not in self.todo):
                if await self.checkRecursion(url) == False:
                    self.todo.add(url)
                    await self.sem.acquire()
                    task = asyncio.ensure_future(self.process(url))
                    task.add_done_callback(lambda t: self.sem.release())
                    task.add_done_callback(self.tasks.remove)
                    self.tasks.add(task)

    async def process(self, url):
        print('processing:', url)
        await self.writeToFile(url)
        self.todo.remove(url)
        self.busy.add(url)
        try:
            resp = await self.session.get(url, ssl=sslcontext)
        except Exception as exc:
            print('...', url, 'has error', repr(str(exc)))
            self.done[url] = False
        else:
            if (resp.status == 200 and
                    ('text/html' in resp.headers.get('content-type'))):
                data = (await resp.read()).decode('utf-8', 'replace')
                urls = re.findall(r'(?i)href=["\']?([^\s"\'<>]+)', data)
                jss = re.findall(r'(?i)src=["\']?([^\s"\'<>]+)', data)
                asyncio.Task(self.addurls([(u, url) for u in urls]))
                asyncio.Task(self.addurls([(u,url) for u in jss]))

            resp.close()
            self.done[url] = True

        self.busy.remove(url)
        print(len(self.done), 'completed tasks,', len(self.tasks),
              'still pending, todo', len(self.todo))

def main():
    loop = asyncio.get_event_loop()

    c = Crawler(sys.argv[1])
    asyncio.ensure_future(c.run())

    try:
        loop.add_signal_handler(signal.SIGINT, loop.stop)
    except RuntimeError:
        pass
#    loop.run_forever()
    loop.run_until_complete(c.run())
    print('todo:', len(c.todo))
    print('busy:', len(c.busy))
    print('done:', len(c.done), '; ok:', sum(c.done.values()))
    print('tasks:', len(c.tasks))


if __name__ == '__main__':
    main()
