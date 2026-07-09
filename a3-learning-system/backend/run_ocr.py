import io,os,re,subprocess,sys,tempfile,time
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
import pdfplumber
from PIL import Image
import numpy as np
from chromadb import PersistentClient
from chromadb.config import Settings

TESS=r'C:\Program Files\Tesseract-OCR\tesseract.exe'
PDF_BASE='E:/code/github_clone/pdf-计算机专业资源/Some-Many-Books/PDF-file'
MAT='app/scripts/knowledge_materials'
DONE='ocr_done.txt'

def ocr(page):
    try:
        t=page.extract_text()
        if t and len(t.strip())>10:return t.strip()
    except:pass
    try:
        img=page.to_image(resolution=150)
        pil=Image.fromarray(np.array(img.original))
        with tempfile.NamedTemporaryFile(suffix='.png',delete=False) as f: pil.save(f.name)
        o=f.name.replace('.png','')
        subprocess.run([TESS,f.name,o,'-l','chi_sim+eng','--psm','6'],capture_output=True,text=True,timeout=25)
        os.unlink(f.name);tf=o+'.txt'
        if os.path.exists(tf):
            with open(tf,encoding='utf-8') as fp:r=fp.read().strip()
            os.unlink(tf);return r
    except:pass
    return ''

client=PersistentClient(path=os.path.abspath('chroma_data_local'),settings=Settings(anonymized_telemetry=False))
try:col=client.get_collection('knowledge_base')
except:col=client.create_collection('knowledge_base')

done=set()
for df in ['pdf_ingest_done.txt','ocr_done.txt','brute_done.txt']:
    if os.path.exists(df):
        with open(df,encoding='utf-8') as f:
            for l in f:
                l=l.strip().split()[0] if l.strip() else ''
                if l:done.add(l)

todo=[]
for root,dirs,files in os.walk(PDF_BASE):
    subj=os.path.basename(root)
    for f in sorted(files):
        if f.lower().endswith('.pdf'):
            k=f'{subj}/{f}'
            if k not in done:todo.append((subj,f,os.path.join(root,f),k))
for f in sorted(os.listdir(MAT)):
    if f.lower().endswith('.pdf'):
        k=f'materials/{f}'
        if k not in done:todo.append(('materials',f,os.path.join(MAT,f),k))

print(f'START: {len(todo)} books');t0=time.time();tc=0
for idx,(subj,fn,path,key) in enumerate(todo):
    bt=time.time();title=fn.rsplit('.',1)[0][:60]
    print(f'[{idx+1}/{len(todo)}] {title[:50]}',end=' ',flush=True)
    try:
        pages=[]
        with pdfplumber.open(path) as pdf:
            total=len(pdf.pages)
            for i in range(total):
                t=ocr(pdf.pages[i])
                if t:pages.append(t)
                if (i+1)%100==0:print(f'{i+1}/{total}',end=' ',flush=True)
        if not pages:print('EMPTY');continue
        full='\n\n'.join(pages)
        chunks=[full[s:s+800].strip() for s in range(0,len(full),680) if full[s:s+800].strip()]
        n=0
        for j in range(0,len(chunks),100):
            b=chunks[j:j+100]
            ids=[f'full:{title}:{j+k}' for k in range(len(b))]
            ms=[{'title':title,'source':key,'chunk':j+k} for k in range(len(b))]
            try:col.add(documents=b,embeddings=[[0.0]*1024]*len(b),metadatas=ms,ids=ids);n+=len(b)
            except:
                for k,c in enumerate(b):
                    try:col.add(documents=[c],embeddings=[[0.0]*1024],metadatas=[ms[k]],ids=[ids[k]]);n+=1
                    except:pass
        tc+=n;elapsed=time.time()-bt
        print(f'-> {len(pages)}p/{total} {len(chunks)}c {elapsed:.0f}s [{tc}c]',flush=True)
        with open(DONE,'a',encoding='utf-8') as f:f.write(key+'\n')
    except Exception as e:
        print(f'ERROR: {e}',flush=True);traceback.print_exc()
        with open(DONE,'a',encoding='utf-8') as f:f.write(key+' ERROR\n')
tt=time.time()-t0
print(f'\nDONE: {len(todo)} books, {tc} chunks, KB:{col.count()}, {tt:.0f}s ({tt/3600:.1f}h)')
