import React,{useState,useRef,useEffect,useCallback} from 'react';
import{Send,Loader2}from 'lucide-react';
async function getToken(){
  let t=localStorage.getItem('nt');if(t)return t;
  try{
    let r=await fetch('/api/auth/login/user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'demo@nexa.com',password:'demo1234'})});
    if(!r.ok)r=await fetch('/api/auth/register/user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'demo@nexa.com',password:'demo1234',tier:'free'})});
    const d=await r.json();localStorage.setItem('nt',d.access_token);return d.access_token;
  }catch(e){return null;}
}
export default function CustomerChat(){
  const[msgs,setMsgs]=useState([{role:'assistant',content:'Hi! I am NexaAgent AI. How can I help you today?'}]);
  const[input,setInput]=useState('');const[loading,setLoading]=useState(false);
  const[convId,setConvId]=useState(null);const[ready,setReady]=useState(false);
  const bottom=useRef(null);
  useEffect(()=>{getToken().then(t=>{if(t)setReady(true);});},[]);
  useEffect(()=>{bottom.current?.scrollIntoView({behavior:'smooth'});},[msgs]);
  const send=useCallback(async()=>{
    const text=input.trim();if(!text||loading||!ready)return;
    setInput('');setLoading(true);
    setMsgs(p=>[...p,{role:'user',content:text},{role:'assistant',content:'...',id:'loading'}]);
    try{
      const token=await getToken();
      const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},body:JSON.stringify({user_id:'demo',conversation_id:convId,message:text})});
      const data=await res.json();
      if(data.conversation_id)setConvId(data.conversation_id);
      setMsgs(p=>p.map(m=>m.id==='loading'?{role:'assistant',content:data.response||'Sorry, try again.'}:m));
    }catch(e){setMsgs(p=>p.map(m=>m.id==='loading'?{role:'assistant',content:'Error: '+e.message}:m));}
    setLoading(false);
  },[input,loading,convId,ready]);
  return(
    <div style={{display:'flex',flexDirection:'column',height:'100vh',maxWidth:'672px',margin:'0 auto',fontFamily:'sans-serif'}}>
      <div style={{background:'white',borderBottom:'1px solid #e5e7eb',padding:'16px 24px',display:'flex',alignItems:'center',gap:'12px'}}>
        <div style={{width:'36px',height:'36px',borderRadius:'50%',background:'#0ea5e9',display:'flex',alignItems:'center',justifyContent:'center',color:'white',fontWeight:'bold'}}>N</div>
        <div><p style={{fontWeight:600,fontSize:'14px',margin:0}}>NexaAgent Support</p><p style={{fontSize:'12px',color:'#6b7280',margin:0}}>AI-powered</p></div>
        <div style={{marginLeft:'auto',display:'flex',alignItems:'center',gap:'6px'}}><span style={{width:'8px',height:'8px',borderRadius:'50%',background:ready?'#4ade80':'#facc15',display:'inline-block'}}></span><span style={{fontSize:'12px',color:'#6b7280'}}>{ready?'Online':'Connecting...'}</span></div>
      </div>
      <div style={{flex:1,overflowY:'auto',padding:'16px'}}>
        {msgs.map((m,i)=><div key={i} style={{display:'flex',justifyContent:m.role==='user'?'flex-end':'flex-start',marginBottom:'12px'}}>
          <div style={{maxWidth:'70%',padding:'10px 16px',borderRadius:'18px',fontSize:'14px',background:m.role==='user'?'#0ea5e9':'white',color:m.role==='user'?'white':'#1f2937',border:m.role==='user'?'none':'1px solid #e5e7eb'}}>{m.content}</div>
        </div>)}
        <div ref={bottom}/>
      </div>
      <div style={{borderTop:'1px solid #e5e7eb',background:'white',padding:'12px 16px'}}>
        <div style={{display:'flex',gap:'8px'}}>
          <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')send();}} placeholder={ready?'Type your message...':'Connecting...'} disabled={loading||!ready} style={{flex:1,border:'1px solid #e5e7eb',borderRadius:'12px',padding:'10px 16px',fontSize:'14px',outline:'none'}}/>
          <button onClick={send} disabled={loading||!input.trim()||!ready} style={{background:'#0ea5e9',color:'white',border:'none',borderRadius:'12px',padding:'10px 14px',cursor:'pointer',opacity:loading||!input.trim()||!ready?0.5:1}}>Send</button>
        </div>
      </div>
    </div>
  );
}
