import { useCallback, useEffect, useRef, useState } from 'react';
import { RobotViewer, type CompareEntry, type RobotImport } from './RobotViewer';
import { FloatingPanel } from './FloatingPanel';
import { ModelingWorkspace } from './ModelingWorkspace';
import { sourceXml, parse, rootLink, locate, insertModule, connectModule, removeBranch, type NodeSelection, type SurfacePoint } from './urdfEditing';
export type LibraryEntry = {id:string; name:string; report:RobotImport};
export function UrdfWorkbench({ initialReport, compareEntries = [], activeCompareId = null, textureEnabled = {}, onSelectCompare, onRemoveCompare, onReportChange }: {
  initialReport: RobotImport | null; compareEntries?: CompareEntry[]; activeCompareId?: string | null; textureEnabled?: Record<string, boolean>;
  onSelectCompare?: (id: string) => void; onRemoveCompare?: (id: string) => void;
  onReportChange?: (report: RobotImport) => void;
}) {
  const [report,setReport]=useState(initialReport);
  const [history,setHistory]=useState<RobotImport[]>(initialReport?[initialReport]:[]);
  const [cursor,setCursor]=useState(0);
  const [xml,setXml]=useState(''); const [saved,setSaved]=useState('');
  const [selected,setSelected]=useState<NodeSelection|null>(null);
  const [library,setLibrary]=useState<LibraryEntry[]>([]);
  const [panels,setPanels]=useState({code:false,library:false,agent:false,compare:false});
  const [unit,setUnit]=useState<'mm'|'m'>('mm');
  const [busy,setBusy]=useState(false); const [error,setError]=useState(''); const [notice,setNotice]=useState('');
  const [pending,setPending]=useState<{child:string;joint:string;original:string[]}|null>(null);
  const [points,setPoints]=useState<SurfacePoint[]>([]);
  const [jointType,setJointType]=useState<'fixed'|'continuous'>('fixed');
  const [axis,setAxis]=useState('0 0 1');
  const [deleteOpen,setDeleteOpen]=useState(false);
  const editor=useRef<HTMLTextAreaElement>(null);
  const dirty=xml!==saved;
  useEffect(()=>{setReport(initialReport);setHistory(initialReport?[initialReport]:[]);setCursor(0);setPending(null);setPoints([]);setSelected(null);},[initialReport]);
  useEffect(()=>{
    let active=true;
    if(!report){setXml('');setSaved('');return;}
    sourceXml(report).then(text=>{if(active){setXml(text);setSaved(text);}}).catch(e=>{if(active)setError(String(e));});
    return()=>{active=false;};
  },[report]);
  async function refreshLibrary(){if(window.urdftools)setLibrary(await window.urdftools.cadLibraryList());}
  useEffect(()=>{void refreshLibrary().catch(e=>setError(String(e)));},[]);
  useEffect(()=>{
    if(!selected || !panels.code || !editor.current) return;
    const range=locate(xml,selected);if(!range)return;
    editor.current.focus();editor.current.setSelectionRange(range.start,range.end);
    editor.current.scrollTop=Math.max(0,(xml.slice(0,range.start).split('\n').length-4)*20);
  },[selected,panels.code]);
  const select=useCallback((next:NodeSelection)=>{setSelected(next);setPanels(p=>({...p,code:true,library:false,agent:false}));},[]);
  const pick=useCallback((point:SurfacePoint)=>{
    if(!pending)return;
    setError('');
    setPoints(old=>{
      if(old.length===0 || old.length===2){
        if(!pending.original.includes(point.link)){setError('先点击原模型的连接位置');return [];}
        return [point];
      }
      if(point.link!==pending.child){setError('第二步请点击新 CAD 模块的连接位置');return old;}
      return [old[0],point];
    });
  },[pending]);
  async function run(action:()=>Promise<void>){if(busy)return;setBusy(true);setError('');setNotice('');try{await action();}catch(e){setError(String(e));}finally{setBusy(false);}}
  function commit(next:RobotImport){setHistory(h=>[...h.slice(0,cursor+1),next]);setCursor(history.length?cursor+1:0);setReport(next);setSelected(null);onReportChange?.(next);}
  async function apply(text:string, baseline=report){
    parse(text);
    if(!window.urdftools)throw new Error('请在桌面应用中编辑');
    return window.urdftools.workbenchApply(text,baseline);
  }
  async function add(entry:LibraryEntry){
    if(dirty)throw new Error('请先应用或还原代码编辑');
    if(pending)throw new Error('请先完成或取消当前连接');
    if(!report){commit(entry.report);setPanels(p=>({...p,library:false}));return;}
    const base=await sourceXml(report,true), module=await sourceXml(entry.report,true);
    const staged=insertModule(base,module);
    const next=await apply(staged.xml);
    setPending({child:staged.child,joint:staged.joint,original:Array.from(parse(base).documentElement.children).filter(e=>e.tagName==='link').map(e=>e.getAttribute('name')!)});setPoints([]);setReport(next);
    setPanels(p=>({...p,library:false}));
  }
  function cancelConnection(){setPending(null);setPoints([]);setReport(history[cursor]);}
  return <div className="urdf-workbench" onDragOver={event=>{if(event.dataTransfer.types.includes('application/x-urdf-cad')){event.preventDefault();event.stopPropagation();}}}
    onDrop={event=>{const id=event.dataTransfer.getData('application/x-urdf-cad');if(!id)return;event.preventDefault();event.stopPropagation();const entry=library.find(e=>e.id===id);if(entry)void run(()=>add(entry));}}>
    <div className="workbench-toolbar" aria-label="URDF 编辑工具">
      <button onClick={()=>setPanels(p=>({...p,code:!p.code,library:false,agent:false}))} aria-pressed={panels.code}>URDF 代码</button>
      <button onClick={()=>setPanels(p=>({...p,library:!p.library,code:false,agent:false}))} aria-pressed={panels.library}>CAD 模块库</button>
      <button onClick={()=>setPanels(p=>({...p,compare:!p.compare}))} aria-pressed={panels.compare}>对比查看 {compareEntries.length || ''}</button>
      <button onClick={()=>setPanels(p=>({...p,agent:!p.agent,code:false,library:false}))} aria-pressed={panels.agent}>Agent 生成 CAD</button>
      <button disabled={busy||dirty||!!pending||cursor<=0} onClick={()=>{setCursor(cursor-1);setReport(history[cursor-1]);onReportChange?.(history[cursor-1]);}}>撤销</button>
      <button disabled={busy||dirty||!!pending||cursor>=history.length-1} onClick={()=>{setCursor(cursor+1);setReport(history[cursor+1]);onReportChange?.(history[cursor+1]);}}>重做</button>
      <button disabled={!report||busy||dirty||!!pending} onClick={()=>void run(async()=>{const result=await window.urdftools!.workbenchExport(report!.operation_id);if(result)setNotice('已导出 URDF 和全部引用资源');})}>导出 URDF 包</button>
    </div>
    {report ? <RobotViewer report={report} textureEnabled={textureEnabled} compareReports={compareEntries.filter(entry=>entry.id!==activeCompareId)} onSelect={select} picking={!!pending} onSurfacePick={pick}/> : <div className="empty-stage"><h2>URDF 查看与构建</h2><p>打开机器人模型，或从 CAD 模块库添加第一个模块</p><p>左键旋转 · 右键平移 · 滚轮缩放</p></div>}
    {panels.compare && <FloatingPanel title="对比查看" initial={{x:Math.max(310,window.innerWidth-390),y:75,width:340,height:365}} onClose={()=>setPanels(p=>({...p,compare:false}))} className="compare-window">
      <section aria-label="URDF 对比查看" className="comparison-panel">
        <p>拖入多个 URDF、ZIP 或模型文件夹；所有模型会在同一网格地面并排显示。选择后，结构、关节、代码和测量只操作该模型。</p>
        {!compareEntries.length && <p>尚未加入模型。</p>}
        {compareEntries.map((entry,index)=><article key={entry.id} data-compare-model={entry.id} data-active={entry.id===activeCompareId}>
          <div><span className="compare-index">{String(index+1).padStart(2,'0')}</span><strong>{entry.report.models.find(model=>model.path===entry.report.selected_model)?.name || entry.report.selected_model}</strong></div>
          <div className="compare-actions"><button type="button" aria-pressed={entry.id===activeCompareId} disabled={busy||dirty||!!pending} onClick={()=>onSelectCompare?.(entry.id)}>{entry.id===activeCompareId?'当前操作':'操作此模型'}</button>
          <button type="button" aria-label={`移除对比 ${entry.report.selected_model}`} disabled={busy||dirty||!!pending} onClick={()=>onRemoveCompare?.(entry.id)}>移除</button></div>
        </article>)}
      </section>
    </FloatingPanel>}
    {(busy||error||notice) && <div className="workbench-notice" role={error?'alert':'status'}>{busy?'正在校验并加载模型…':error||notice}</div>}
    {panels.code && <FloatingPanel title="编辑 · URDF" initial={{x:28,y:105,width:520,height:550}} onClose={()=>setPanels(p=>({...p,code:false}))} className="urdf-code-panel">
      <div className="workbench-actions"><span>{dirty?'未应用':'已载入'}{selected?' · '+selected.name:''}</span>
        <button disabled={!dirty||busy||!!pending} onClick={()=>void run(async()=>{commit(await apply(xml));setNotice('代码已校验并保存为新版本');})}>应用并预览</button>
        <button disabled={!dirty||busy} onClick={()=>setXml(saved)}>还原编辑</button>
        <button disabled={!selected||busy||dirty||!!pending} onClick={()=>setDeleteOpen(true)}>删除选中子树</button></div>
      <label className="sr-only" htmlFor="urdf-source">URDF 源代码</label>
      <textarea id="urdf-source" ref={editor} spellCheck={false} value={xml} disabled={!report||busy||!!pending} onChange={e=>setXml(e.target.value)} />
      <p className="hint">点击模型关节或结构节点，自动定位并选中对应代码。应用失败会保留草稿和上一版模型。</p>
      {deleteOpen && <div role="alert"><p>删除 {selected?.name} 及其全部后代 Link / Joint？可撤销。</p><button disabled={busy} onClick={()=>void run(async()=>{if(selected)commit(await apply(removeBranch(xml,selected)));setDeleteOpen(false);})}>确认删除</button><button onClick={()=>setDeleteOpen(false)}>取消</button></div>}
    </FloatingPanel>}
    {panels.library && <FloatingPanel title="CAD 模块库" initial={{x:20,y:100,width:320,height:480}} onClose={()=>setPanels(p=>({...p,library:false}))}>
      <p>导入后保存在本机。拖入场景或点击“添加”。</p>
      <label>STL / OBJ 原始单位 <select value={unit} onChange={e=>setUnit(e.target.value as 'mm'|'m')}><option value="mm">毫米</option><option value="m">米</option></select></label>
      <button disabled={busy||!window.urdftools} onClick={()=>void run(async()=>{const entry=await window.urdftools!.cadLibraryImport(unit);if(entry)await refreshLibrary();})}>导入 STEP / STL / OBJ</button>
      <p className="hint">STEP 使用文件单位。模块保留真实几何；质量、惯量和碰撞体需要另行设置。</p>
      {!library.length && <p>模块库为空，导入 CAD 或让 Agent 生成。</p>}
      {library.map(entry=><article className="cad-library-item" key={entry.id} draggable={!busy&&!pending} onDragStart={e=>e.dataTransfer.setData('application/x-urdf-cad',entry.id)}>
        <strong>{entry.name}</strong><div><button disabled={busy||dirty||!!pending} onClick={()=>void run(()=>add(entry))}>添加</button>
        <button disabled={busy} onClick={()=>void run(async()=>{await window.urdftools!.cadLibraryRemove(entry.id);await refreshLibrary();})}>移出库</button></div>
      </article>)}
    </FloatingPanel>}
    {pending && <FloatingPanel title="连接 CAD 模块" initial={{x:20,y:90,width:335,height:310}}>
      <p>{points.length===0?'① 点击原模型上的连接位置':points.length===1?'② 点击新模块上的连接位置':'③ 两个连接位置已选好，确认后按表面法向对齐'}</p>
      <p>原模型：{points[0]?.link||'待选择'}<br/>新模块：{points[1]?.link||pending.child}</p>
      <div className="workbench-actions"><button disabled={points.length!==0} onClick={()=>setPoints([{link:pending.original[0],point:[0,0,0],normal:[0,0,1]}])}>原模型根部中心</button>
      <button disabled={points.length!==1} onClick={()=>setPoints(old=>[old[0],{link:pending.child,point:[0,0,0],normal:[0,0,-1]}])}>新模块中心</button></div>
      <label>连接方式 <select value={jointType} onChange={e=>setJointType(e.target.value as 'fixed'|'continuous')}><option value="fixed">固定连接</option><option value="continuous">连续旋转关节</option></select></label>
      {jointType==='continuous'&&<label>旋转方向 <select value={axis} onChange={e=>setAxis(e.target.value)}><option value="1 0 0">X</option><option value="0 1 0">Y</option><option value="0 0 1">Z</option></select></label>}
      <p className="hint">也可用按钮选中心点。仅建立几何连接，不推断电机、限位或材料。需要限位时可在代码中设置。</p>
      <button disabled={points.length!==2||busy} onClick={()=>void run(async()=>{const text=connectModule(await sourceXml(report!,true),pending.joint,points[0],points[1],jointType,axis);const next=await apply(text);commit(next);setPending(null);setPoints([]);setNotice('连接已保存，可撤销或在代码中修改');})}>确认连接</button>
      <button disabled={busy} onClick={()=>setPoints([])}>重新选点</button><button disabled={busy} onClick={cancelConnection}>取消添加</button>
    </FloatingPanel>}
    {panels.agent && <FloatingPanel title="Agent · CAD 模块" initial={{x:28,y:95,width:460,height:560}} onClose={()=>setPanels(p=>({...p,agent:false}))}>
      <ModelingWorkspace libraryOnly onLibraryChange={()=>void refreshLibrary().catch(e=>setError(String(e)))}/>
    </FloatingPanel>}
  </div>;
}
