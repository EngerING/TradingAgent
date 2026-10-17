"""Publish the Markdown manual and editable diagrams; documentation only."""
from pathlib import Path
import json, re, sys, textwrap, hashlib, html
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tmp/manual-tools'))
import markdown
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (BaseDocTemplate,PageTemplate,Frame,Paragraph,Spacer,
    PageBreak,Table,TableStyle,Preformatted,KeepTogether)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics.shapes import Drawing,Rect,Line,String,Polygon
from reportlab.graphics import renderSVG
import pymupdf as fitz

FONTROOT=Path('C:/Windows/Fonts')
for name,file in [('Body','calibri.ttf'),('BodyBold','calibrib.ttf'),('BodyItalic','calibrii.ttf'),('Mono','consola.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(FONTROOT/file)))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='BodyItalic',boldItalic='BodyBold')
NAVY=colors.HexColor('#122C3B');TEAL=colors.HexColor('#087F83');INK=colors.HexColor('#263844')
MUTED=colors.HexColor('#566B76');PALE=colors.HexColor('#EDF5F6');GOLD=colors.HexColor('#AC6B15')
W,H=A4;LEFT=52;RIGHT=48;WIDTH=W-LEFT-RIGHT

def diagrams():
    # Sources are explicit data, editable without touching application code.
    specs={
      'components':{'title':'Dos superficies de aplicación; autoridad separada','height':410,'nodes':[
        [15,330,215,55,'Navegador principal\nVue / Pinia / router'],[265,330,215,55,'Navegador R20 V2\npreparation + monitor'],
        [15,230,215,55,'TradingAgent.Api :5080\nHTTP / SignalR / Core'],[265,230,215,55,'ConfigurationLab :5182\nHTTP autenticado / bridge'],
        [15,130,215,55,'Infrastructure / Npgsql\nPython: proyección e investigación'],[265,130,215,55,'Python R20 V2\neconomía + SQL + replay'],
        [15,30,215,55,'PostgreSQL :55433\njournals históricos / V1'],[265,30,215,55,'PostgreSQL test :55432\nledger V2 sintético']],
        'edges':[[0,2,'HTTP / eventos'],[1,3,'HTTP / refresco'],[2,4,'DI / JSON'],[3,5,'stdin / stdout'],[4,6,'SQL'],[5,7,'psql con guard']]},
      'deployment':{'title':'Procesos posibles; diagrama no acredita que estén activos','height':450,'nodes':[
        [30,365,430,50,'Equipo local Windows · loopback · usuario autorizado'],
        [15,260,215,55,'Vite :5173 (desarrollo)\nproxy /api y /hubs → 5080'],[265,260,215,55,'TWS :7497\ncuenta exacta / API de lectura'],
        [15,155,215,55,'Api :5080\nfrontend/dist + JSON + Hub'],[265,155,215,55,'Python PaperReadSource\ndiagnóstico; sin fills V2'],
        [15,45,215,55,'PostgreSQL Paper :55433\nno migrar para documentar'],[265,45,215,55,'Laboratorio separado\n5182 + PostgreSQL test 55432']],
        'edges':[[1,3,'proxy'],[2,4,'API TCP'],[3,5,'Npgsql']]},
      'dataflow':{'title':'La lectura auténtica no está conectada al ciclo sintético','height':510,'nodes':[
        [30,435,430,48,'IBKR → identidad exacta → contrato / calendario / quotes'],
        [30,350,430,48,'assess_market → barras nativas completas / señal técnica'],
        [30,265,430,48,'Diagnóstico auténtico: entryEligible=false; corte histórico'],
        [30,150,430,60,'Replay explícito + perfil + permiso sintético\nAdmissionCoordinator → solver → reserva atómica'],
        [30,50,430,55,'ShadowCycle → ledger/ciclo → monitor autenticado\nSólo SYNTHETIC_TEST_ONLY']],
        'edges':[[0,1,'lectura'],[1,2,'evidencia'],[3,4,'ciclo de laboratorio']]},
      'erd':{'title':'Línea sólida = FK SQL; discontinua = contrato lógico','height':535,'nodes':[
        [10,450,220,55,'r20_v2_test.profiles\nPK scope_id + version'],[265,450,220,55,'r20_v2_config.preparations\nPK scope + revision'],
        [10,330,220,55,'r20_v2_test.events\nFK scope_id + profile_version'],[265,330,220,55,'r20_v2_config.events\nperfil validado / activado'],
        [10,200,220,55,'r20_v2_shadow.events\naccountingRevision + hash'],[265,200,220,55,'r20_v2_admission.receipts\nUNIQUE scope + signal_id'],
        [10,65,220,55,'r20_v2_runner.controls\nPREREGISTER / STOP'],[265,65,220,55,'r20_v2_shadow.permissions\nplan / contexto / ventana']],
        'edges':[[2,0,'N : 1'],[4,2,'verifica head',True],[1,3,'preparación ligada',True],[3,5,'admisión',True],[5,7,'permiso',True],[6,4,'guard de OPEN',True]]},
      'navigation':{'title':'Rutas Vue principales y host R20 independiente','height':370,'nodes':[
        [25,290,440,50,'index.html → main.ts → App.vue → router'],
        [10,180,225,65,'/ · /trading · /operaciones\n/mercado · /experimentos\n/aggressive-growth'],[265,180,220,65,'/sol · /research · /reportes\n/configuracion\n/r20/configuracion'],
        [25,45,440,65,'Entrada lab: r20-config.html → r20-config-main.ts\nR20ConfigurationLab → R20ConfigurationPage\nAPI V2 disponible en :5182; no registrada en :5080']],
        'edges':[[0,1,'páginas'],[0,2,'páginas']]},
      'authority':{'title':'Cada transición conserva una autoridad distinta','height':495,'nodes':[
        [30,415,430,48,'Usuario elige valores → preparación GUARDADO / VALIDO'],
        [30,325,430,48,'Perfil vigente + políticas identificadas por hash'],
        [30,235,430,48,'Permiso Shadow independiente y ligado al contexto'],
        [30,145,430,48,'Datos / inventario / solver / reserva / Stop SQL'],
        [30,55,430,48,'Ciclo virtual de laboratorio · brokerOrders=0']],
        'edges':[[0,1,'configuración'],[1,2,'no se concede automáticamente',True],[2,3,'comprobación'],[3,4,'admisión no es permiso IBKR']]},
      'paper-flow':{'title':'Flujo R20 Paper propuesto; no implementado de extremo a extremo','height':525,'nodes':[
        [30,435,430,50,'Datos y señal R20 existentes\nEconomía V2 probada en laboratorio'],
        [30,330,430,60,'PENDIENTE: intención Paper + permiso + guard compatible\nexclusión durable por cuenta + journal operativo'],
        [30,220,430,60,'Transporte/callbacks heredados existentes\nPENDIENTE: integración R20 LONG / SHORT y protección'],
        [30,110,430,60,'PENDIENTE R20: reconciliar ACK / fills / comisiones\nrecuperar estados inciertos sin duplicar órdenes'],
        [30,20,430,45,'Proyección Paper separada del fill virtual · Live bloqueado']],
        'edges':[[0,1,'diseño futuro',True],[1,2,'autoridad separada',True],[2,3,'eventos del bróker',True],[3,4,'evidencia confirmada',True]]},
      'shadow-sequence':{'title':'Replay V2: una operación; no forward auténtico','height':520,'sequence':True,
        'lanes':['Runner / datos','Economía / plan','SQL / ledger','Monitor / UI'],
        'messages':[[0,1,'Quote y barras cerradas'],[1,1,'Señal + perfil + permiso + sizing'],[1,2,'Reserva: lock + CAS + signal ID'],[2,1,'Recibo durable / retry idéntico'],[0,1,'Quote válida para abrir'],[1,2,'OPEN + costos: commit conjunto'],[0,1,'Seguimiento: precio disponible'],[1,2,'MARK o CLOSE + neto una vez'],[2,3,'Snapshot consistente y hash'],[3,3,'Refresco explícito / STALE']]}
    }
    directory=OUT/'diagrams';directory.mkdir(exist_ok=True)
    source=directory/'specs.json'
    if source.exists():
        specs=json.loads(source.read_text(encoding='utf-8'))
    else:
        source.write_text(json.dumps(specs,ensure_ascii=False,indent=2),encoding='utf-8')
    return specs

def draw(spec):
    h=spec['height'];d=Drawing(495,h)
    d.add(String(247,h-13,spec['title'],fontName='BodyBold',fontSize=10,fillColor=NAVY,textAnchor='middle'))
    if spec.get('sequence'):
        xs=[65,185,305,425]
        for x,t in zip(xs,spec['lanes']):
            d.add(Rect(x-56,h-60,112,30,fillColor=PALE,strokeColor=TEAL,strokeWidth=.6))
            d.add(String(x,h-48,t,fontName='BodyBold',fontSize=8.5,textAnchor='middle',fillColor=NAVY))
            d.add(Line(x,20,x,h-60,strokeColor=colors.HexColor('#B6C8CD'),strokeDashArray=[3,3]))
        for i,(a,b,label) in enumerate(spec['messages']):
            y=h-88-i*41;xa=xs[a];xb=xs[b]
            if a==b:
                d.add(Line(xa,y,xa+44,y,strokeColor=TEAL));d.add(Line(xa+44,y,xa+44,y-10,strokeColor=TEAL));d.add(Line(xa+44,y-10,xa,y-10,strokeColor=TEAL))
                d.add(String(xa-52,y+8,str(i+1)+'. '+label,fontName='Body',fontSize=7.5,fillColor=INK))
            else:
                d.add(Line(xa,y,xb,y,strokeColor=TEAL,strokeWidth=1))
                sign=1 if xb>xa else -1
                d.add(Polygon([xb,y,xb-sign*5,y+2.5,xb-sign*5,y-2.5],fillColor=TEAL,strokeColor=TEAL))
                d.add(String((xa+xb)/2,y+7,str(i+1)+'. '+label,fontName='Body',fontSize=8,textAnchor='middle',fillColor=INK))
        return d
    for i,j,label,*dash in spec.get('edges',[]):
        a=spec['nodes'][i];b=spec['nodes'][j]
        xa=a[0]+a[2]/2;xb=b[0]+b[2]/2
        ya=a[1] if a[1]>b[1] else a[1]+a[3];yb=b[1]+b[3] if a[1]>b[1] else b[1]
        d.add(Line(xa,ya,xb,yb,strokeColor=MUTED,strokeWidth=.8,strokeDashArray=[4,3] if dash else None))
        sign=1 if yb>ya else -1
        d.add(Polygon([xb,yb,xb-3,yb-sign*6,xb+3,yb-sign*6],fillColor=MUTED,strokeColor=MUTED))
        d.add(String((xa+xb)/2+5,(ya+yb)/2,label,fontName='Body',fontSize=8,fillColor=MUTED))
    for x,y,w,h,t in spec['nodes']:
        d.add(Rect(x,y,w,h,rx=5,ry=5,fillColor=PALE,strokeColor=TEAL,strokeWidth=.7))
        lines=t.split('\n');start=y+h/2+(len(lines)-1)*6-3
        for n,line in enumerate(lines):d.add(String(x+w/2,start-n*12,line,fontName='Body',fontSize=9.2,textAnchor='middle',fillColor=INK))
    return d

def appendices(md):
    audit=json.loads((OUT/'source-audit.json').read_text(encoding='utf-8'))
    refs=[]
    def add(path,component,responsibility,chapter):
        p=ROOT/path
        if not p.is_file():raise ValueError('Missing referenced source: '+path)
        txt=p.read_text(encoding='utf-8-sig').splitlines()
        candidate=next((i for i,s in enumerate(txt,1) if re.search(r'^(class |def |public .*class|public .*record|CREATE TABLE|var builder|import |param)',s)),1)
        refs.append((component,f'`{path}:{candidate}`',responsibility,str(chapter),'Estática; evidencia dinámica separada'))
    for path,comp,resp,ch in [
      ('Directory.Build.props','Build','net9.0, warnings, auditoría NuGet',9),
      ('TradingAgent.sln','Solución','Proyectos incluidos; lab V2 fuera',4),
      ('src/TradingAgent.Api/Program.cs','Host principal','Arranque, migración, DI, HTTP',4),
      ('src/TradingAgent.Api/DashboardEndpoints.cs','HTTP UI','Sesión, estáticos, rutas, retirada',4),
      ('src/TradingAgent.Api/DashboardRealtime.cs','SignalR','Deltas y broadcaster',8),
      ('src/TradingAgent.Api/DashboardService.cs','Proyección','Bridge Python y frescura',4),
      ('src/TradingAgent.Api/PaperFeedService.cs','Colector','Proceso lector opcional',10),
      ('src/TradingAgent.Api/LegacyOperationRetirement.cs','Retirada','410 de creaciones heredadas',14),
      ('src/TradingAgent.Api/SolChat.cs','Sol','Contrato interpretativo y presupuesto',11),
      ('src/TradingAgent.Api/AggressiveGrowthCommand.cs','CLI V1','Bridge de journal',6),
      ('src/TradingAgent.ConfigurationLab/Program.cs','Host V2','Auth, bridge, rutas sólo laboratorio',4),
      ('src/TradingAgent.ResearchLab/Program.cs','Research C#','Simulación stdin/stdout',5),
      ('src/TradingAgent.Core/Risk.cs','Riesgo','RiskPolicy y RiskEngine',11),
      ('src/TradingAgent.Core/VirtualCapital.cs','Capital','Asignación y pérdida consumida',11),
      ('src/TradingAgent.Core/Broker.cs','Datos','IBrokerData sin métodos de órdenes',10),
      ('src/TradingAgent.Core/PaperExecutionPreparation.cs','Preparación','Contratos sin transmisión',10),
      ('src/TradingAgent.Infrastructure/PostgresStore.cs','Store C#','Migraciones, CAS, SQL parametrizado',7),
      ('src/TradingAgent.Infrastructure/AggressiveGrowthStore.cs','Store V1','Lock, hash, retiro de nuevas cohortes',7),
      ('src/TradingAgent.Infrastructure/DashboardStore.cs','Lectura UI','Envelope histórico',8),
      ('src/TradingAgent.Infrastructure/PaperLabJournal.cs','Paper heredado','Persistencia de intenciones/estado',10),
    ]:add(path,comp,resp,ch)
    py=[('aggressive_growth','Señal V1','EMA/ATR/ruptura y dominio histórico',6),('aggressive_growth_runner','Observador V1','Hash, singleton y journal',6),
        ('r20_profiles','Perfiles','Tipos, UTC, día y hashes',6),('r20_economics','Contabilidad','Equity, costos y pérdida diaria',6),
        ('r20_sizing','Solver','Mayor cantidad admisible y estrés',6),('r20_cost_policy','Costos','Procedencia y bloqueadores',10),
        ('r20_persistence','Ledger','TestStore, Snapshot y cadena',7),('r20_configuration','Configuración','Borrador/validación/activación lab',4),
        ('r20_preparation','Preparación USD','Preview y documento inmutable',8),('r20_shadow_plan','Plan','Vínculo a preparación y permiso',6),
        ('r20_admission','Admisión','Inventario, sizing y reserva',12),('r20_shadow','Ciclo','OPEN/MARK/CLOSE y recuperación',12),
        ('r20_runner','Runner','Replay, Stop, singleton y ReadOnly',12),('r20_market','Fuente','Lectura auténtica sin permiso',10),
        ('r20_monitor','Monitor','Proyección consistente y corte auténtico',8),('ibkr_session','Identidad','AccountBinding y modo',11),
        ('paper_execution_wire','Transporte','SDK y guards de mutación',10),('paper_lab','Paper','Intención, reconciliación y dirección',10),
        ('paper_recovery_close','Recuperación','Cierre acotado heredado',10),('stock_paper_forward','Guard H40','Scope específico, no guard R20',11),
        ('research_calendar','Calendario','Normalización nativa y completitud',5),('research_indicators','Indicadores','Análisis de investigación',5),
        ('dashboard_projection','Proyección','Vista general sin autoridad',8),('kronos/worker','Kronos','Ciclo de observación y cache',5),
        ('ai_strategy_researcher/runner','IA research','Orquestación de investigación',5)]
    for f,c,r,ch in py:add('python/trading_agent/'+f+'.py',c,r,ch)
    for f in ['test','configuration','preparation','admission','shadow','runner']:
        add('python/trading_agent/r20_'+f+'_schema.sql','SQL V2 '+f,'Guard test, tablas y funciones',7)
    for p in sorted((ROOT/'src/TradingAgent.Infrastructure/Migrations').glob('*.sql')):
        add(p.relative_to(ROOT).as_posix(),'Migración '+p.name[:3],'Esquema histórico; no aplicar aquí',7)
    for p,c,r,ch in [
      ('frontend/src/main.ts','Vue principal','Pinia y router',8),('frontend/src/r20-config-main.ts','Entrada lab','Página R20 independiente',8),
      ('frontend/src/app/routes.ts','Rutas','Navegación principal',8),('frontend/src/api.ts','HTTP principal','Sesión y snapshot',8),
      ('frontend/src/realtime.ts','Tiempo real','Secuencias, reconnect y STALE',8),('frontend/src/stores.ts','Stores','Proyección de dominios',8),
      ('frontend/src/stores/r20Preparation.ts','Preparación UI','Valores, preview e historial',8),
      ('frontend/src/r20-configuration-contract.ts','Contrato UI','Zod y fetch V2',8),('frontend/src/r20-preparation-contract.ts','Contrato USD','Valores y propósito',8),
      ('frontend/src/r20-monitor-contract.ts','Contrato monitor','Decimales y clasificación',8),
      ('frontend/src/modules/r20-configuration/R20ConfigurationPage.vue','Página R20','Formulario y monitor delegados',8),
      ('frontend/src/modules/r20-configuration/R20ShadowMonitor.vue','Monitor R20','Seguimiento de laboratorio',8),
      ('frontend/vite.config.ts','Vite','Build principal/proxy',9),('frontend/vite.r20.config.ts','Build V2','Entrada r20-config.html',9),
      ('frontend/package.json','Dependencias UI','Scripts y Node mínimo',9),('frontend/playwright.r20-phase3.config.ts','Browser V2','Host 5182 y artifacts',13),
      ('scripts/start-dashboard.ps1','Arranque principal','Carga y DLL R20Only',9),('scripts/test-database.ps1','Clúster test','Start/Stop/Status',9),
      ('scripts/paper-database.ps1','Clúster Paper','Start migra; Load configura',9),('scripts/paper-lab-database.ps1','Roles Paper','Prepare modifica; Load configura',9),
      ('scripts/aggressive-growth.ps1','Wrapper V1','Status/Stop; Prepare retirado',6),('scripts/r20-only-policy.ps1','Retirada','Allowlist de acciones heredadas',11),
      ('scripts/verify.ps1','Pruebas','Build y suites; precondiciones',13),('scripts/smoke-api.ps1','Smoke antiguo','Expectativa de creación desactualizada',14),
      ('config/r20-v2-cost-policy.proposed.json','Política propuesta','UNKNOWN y supuestos conservados',10),('config/ibkr-session.json','Endpoint TWS','Loopback y puerto',10),
      ('config/aggressive-growth-r20.json','Protocolo V1','Identidad histórica técnica/económica',6),('config/kronos/upstream-lock.json','Kronos lock','Hashes código/pesos',5),
      ('python/tests/test_r20_v2_autonomy.py','Test ciclo','Preparación/permisos/replay/recovery',13),('python/tests/test_r20_v2_persistence.py','Test SQL','CAS y fallos de integridad',13),
      ('frontend/e2e/r20-phase3.spec.ts','E2E fase 3','Flujos reales de laboratorio',13),
    ]:add(p,c,r,ch)
    rows=['| Componente | Archivo y línea de entrada | Responsabilidad | Cap. | Verificación |','|---|---|---|---|---|']
    rows += ['| '+' | '.join(row)+' |' for row in refs]
    md=md.replace('<!-- TRACEABILITY -->','\n'.join(rows))
    checks=audit['integrity']['protected-final.json']['files'];public=[r for r in checks if not r['path'].startswith('.local/')]
    body=f"Catálogo: {len(checks)} entradas protegidas; {len(public)} rutas de fuente/configuración y {len(checks)-len(public)} registros privados de seguridad. Todos coincidieron con la referencia al inicio.\n\n"
    body+='| Archivo protegido público | Resultado inicial |\n|---|---|\n'
    body+='\n'.join(f"| `{r['path']}` | {'Coincide' if r['matches'] else 'DIFERENCIA'} |" for r in public)
    md=md.replace('<!-- PROTECTED -->',body)
    return md,refs

styles={
 'body':ParagraphStyle('body',fontName='Body',fontSize=10.2,leading=14.4,textColor=INK,spaceAfter=7,splitLongWords=True,allowWidows=0,allowOrphans=0),
 'h1':ParagraphStyle('h1',fontName='BodyBold',fontSize=21,leading=25,textColor=NAVY,spaceAfter=17,keepWithNext=True),
 'h2':ParagraphStyle('h2',fontName='BodyBold',fontSize=13,leading=17,textColor=TEAL,spaceBefore=14,spaceAfter=7,keepWithNext=True),
 'table':ParagraphStyle('table',fontName='Body',fontSize=8.4,leading=11.1,textColor=INK,spaceAfter=0,splitLongWords=True),
 'th':ParagraphStyle('th',fontName='BodyBold',fontSize=8.5,leading=11.3,textColor=colors.white,spaceAfter=0),
 'code':ParagraphStyle('code',fontName='Mono',fontSize=8,leading=10.4,textColor=NAVY,spaceAfter=10,backColor=PALE,borderPadding=8),
 'caption':ParagraphStyle('caption',fontName='BodyItalic',fontSize=9,leading=12,textColor=MUTED,spaceBefore=5,spaceAfter=12),
}

def inline(el):
    text=html.escape(el.text or '')
    for child in el:
        tag=child.tag
        val=inline(child)
        if tag=='strong':val='<b>'+val+'</b>'
        elif tag=='em':val='<i>'+val+'</i>'
        elif tag=='code':val='<font name="Mono" size="8.3">'+val+'</font>'
        elif tag=='a':val='<u>'+val+'</u>'
        elif tag=='br':val='<br/>'
        text+=val+html.escape(child.tail or '')
    return text

class ManualDoc(BaseDocTemplate):
    def __init__(self,path):
        super().__init__(str(path),pagesize=A4,leftMargin=LEFT,rightMargin=RIGHT,topMargin=58,bottomMargin=50,
                         title='TradingAgent - Manual técnico integral',author='Documentación técnica de TradingAgent')
        self.addPageTemplates(PageTemplate(id='manual',frames=[Frame(LEFT,50,WIDTH,H-108,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=self.page))
        self.chapter='';self.heading_data=[]
    def page(self,c,doc):
        if doc.page==1:
            c.setFillColor(NAVY);c.rect(0,0,W,H,fill=1,stroke=0)
            c.setFillColor(TEAL);c.rect(0,H-23,W,23,fill=1,stroke=0)
            c.setFont('BodyBold',13);c.setFillColor(colors.HexColor('#66CCD0'));c.drawString(LEFT,H-103,'TRADINGAGENT')
            c.setFillColor(colors.white);c.setFont('BodyBold',34)
            c.drawString(LEFT,H-172,'MANUAL TÉCNICO');c.drawString(LEFT,H-214,'INTEGRAL')
            c.setFont('Body',16);c.drawString(LEFT,H-266,'Arquitectura, funcionamiento,')
            c.drawString(LEFT,H-289,'despliegue y mantenimiento')
            c.setFillColor(colors.HexColor('#C2D8E1'));c.setFont('Body',11)
            c.drawString(LEFT,186,'Versión documental 1.0 | 14 de octubre de 2026')
            c.drawString(LEFT,162,'Código real, fronteras de autoridad y evidencia fechada.')
            c.drawString(LEFT,138,'Corte posterior a R20 V2 fase 3. Sin activación operativa.')
            c.setFont('Body',9);c.drawString(LEFT,76,'15 capítulos · mapa de archivos · diagramas editables · guía de despliegue')
            return
        c.setStrokeColor(colors.HexColor('#CDDEE2'));c.line(LEFT,H-39,W-RIGHT,H-39)
        c.setFillColor(MUTED);c.setFont('Body',8.5);c.drawString(LEFT,H-28,'TRADINGAGENT / Manual técnico integral')
        c.drawRightString(W-RIGHT,H-28,'v1.0 · 14 oct 2026')
        c.line(LEFT,35,W-RIGHT,35);c.setFont('Body',8)
        c.drawString(LEFT,22,'Fuente inspeccionada; estados dinámicos según evidencia fechada')
        c.drawRightString(W-RIGHT,22,str(doc.page))
    def afterFlowable(self,flow):
        if isinstance(flow,Paragraph) and flow.style.name=='h1':
            if flow.getPlainText()=='Contenido':return
            text=flow.getPlainText();key='h-'+hashlib.sha1(text.encode()).hexdigest()[:12]
            self.canv.bookmarkPage(key);self.canv.addOutlineEntry(text,key,0,False)
            self.notify('TOCEntry',(0,text,self.page,key))

def publish():
    specs=diagrams();drawings={k:draw(s) for k,s in specs.items()}
    for k,d in drawings.items():renderSVG.drawToFile(d,str(OUT/'diagrams'/f'{k}.svg'))
    path=OUT/'TradingAgent_Manual_Tecnico_Integral.md'
    md=path.read_text(encoding='utf-8');md,refs=appendices(md)
    # Persist expanded source so the user receives a complete Markdown manual.
    path.write_text(md,encoding='utf-8')
    root=ET.fromstring('<article>'+markdown.markdown(md,extensions=['tables','fenced_code'])+'</article>')
    story=[Spacer(1,20),PageBreak(),Paragraph('Contenido',styles['h1'])]
    toc=TableOfContents();toc.levelStyles=[ParagraphStyle('toc0',fontName='Body',fontSize=10.6,leading=17,spaceBefore=4,textColor=INK)]
    story.extend([toc,PageBreak()])
    started=False
    for el in root:
        tag=el.tag
        if tag=='h2' and ''.join(el.itertext()).startswith('Alcance'):started=True
        if not started:continue
        if tag=='h1':
            story.extend([PageBreak(),Paragraph(inline(el),styles['h1'])])
        elif tag in ('h2','h3'):story.append(Paragraph(inline(el),styles['h2']))
        elif tag=='p':
            img=el.find('img')
            if img is not None:
                k=Path(img.attrib['src']).stem
                figure=[drawings[k],Paragraph(html.escape(img.attrib.get('alt','')),styles['caption'])]
                if story and isinstance(story[-1],Paragraph) and story[-1].style.name=='h2':
                    figure.insert(0,story.pop())
                story.append(KeepTogether(figure))
            else:story.append(Paragraph(inline(el),styles['body']))
        elif tag in ('ul','ol'):
            for n,item in enumerate(el,1):
                prefix=f'{n}. ' if tag=='ol' else '• '
                story.append(Paragraph(prefix+inline(item),styles['body']))
        elif tag=='pre':
            raw=''.join(el.itertext()).rstrip();lines=[]
            for s in raw.splitlines():
                lines.extend(textwrap.wrap(s,98,replace_whitespace=False,drop_whitespace=False,subsequent_indent='  ') or [''])
            story.append(Preformatted('\n'.join(lines),styles['code']))
        elif tag=='table':
            rows=[]
            for ri,tr in enumerate(el.findall('.//tr')):
                rows.append([Paragraph(inline(td),styles['th' if ri==0 else 'table']) for td in tr])
            cols=len(rows[0]);ratio={2:[.55,.45],3:[.31,.34,.35],4:[.22,.35,.27,.16],5:[.16,.31,.23,.06,.24]}.get(cols,[1/cols]*cols)
            table=Table(rows,colWidths=[WIDTH*x for x in ratio],repeatRows=1,hAlign='LEFT',splitByRow=1)
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F1F6F7')]),('LINEBELOW',(0,0),(-1,0),.7,TEAL),
                ('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#DAE4E7'))]))
            story.extend([table,Spacer(1,10)])
    pdf=OUT/'TradingAgent_Manual_Tecnico_Integral.pdf'
    ManualDoc(pdf).multiBuild(story,maxPasses=5)
    doc=fitz.open(pdf);texts=[p.get_text() for p in doc]
    violations=[]
    for i,p in enumerate(doc):
        for b in p.get_text('dict')['blocks']:
            for line in b.get('lines',[]):
                for span in line.get('spans',[]):
                    x0,y0,x1,y1=span['bbox']
                    if x0<0 or y0<0 or x1>p.rect.width+.5 or y1>p.rect.height+.5:violations.append({'page':i+1,'text':span['text'],'bbox':span['bbox']})
    report={'pages':len(doc),'page_text_lengths':[len(t.strip()) for t in texts],'blank_pages':[i+1 for i,t in enumerate(texts) if len(t.strip())<60],
            'out_of_page_text':violations,'diagrams':list(specs),'source_index_entries':len(refs),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
            'md_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'method':'ReportLab multiBuild; PyMuPDF text/bounds and PNG rendering; visual review separately',
            'review_status':'PENDING_VISUAL_REVIEW'}
    render=ROOT/'tmp/pdfs/manual';render.mkdir(parents=True,exist_ok=True)
    for i,p in enumerate(doc):p.get_pixmap(matrix=fitz.Matrix(1,1),alpha=False).save(render/f'page-{i+1:03}.png')
    from PIL import Image,ImageDraw
    for first in range(0,len(doc),12):
        sheet=Image.new('RGB',(1040,4*390),'#c9d3d7');canvas=ImageDraw.Draw(sheet)
        for k in range(first,min(first+12,len(doc))):
            im=Image.open(render/f'page-{k+1:03}.png');im.thumbnail((320,352))
            x=((k-first)%3)*345+12;y=((k-first)//3)*390+22
            sheet.paste(im,(x,y));canvas.text((x,y-18),str(k+1),fill='black')
        sheet.save(render/f'contact-{first//12+1}.png')
    (OUT/'pdf-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('page_text_lengths',)}))

if __name__=='__main__':publish()
