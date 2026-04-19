import React, { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, AlertCircle } from "lucide-react";

function Bubble({ msg }) {
  const isUser  = msg.role === "user";
  const isAgent = msg.role === "agent";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-brand-500 flex items-center justify-center text-white text-xs font-bold mr-2 shrink-0 mt-1">
          {isAgent ? "A" : "AI"}
        </div>
      )}
      <div className={[
        "max-w-[70%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed shadow-sm",
        isUser ? "bg-brand-500 text-white rounded-tr-sm" : "",
        !isUser && !isAgent ? "bg-white text-gray-800 border border-gray-100 rounded-tl-sm" : "",
        isAgent ? "bg-green-50 text-gray-800 border border-green-200 rounded-tl-sm" : ""
      ].join(" ")}>
        {isAgent && <span className="text-xs text-green-600 font-medium block mb-1">Support Agent</span>}
        {msg.content}
        {msg.streaming && <span className="animate-pulse">|</span>}
      </div>
    </div>
  );
}

const WAIT = { CRITICAL:"<15 min", HIGH:"<1 hr", MEDIUM:"<4 hrs", LOW:"<24 hrs" };

export default function CustomerChat() {
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi! I am the NexaAgent AI. How can I help you today?" }
  ]);
  const [input,          setInput]          = useState("");
  const [loading,        setLoading]        = useState(false);
  const [convId,         setConvId]         = useState(null);
  const [escalated,      setEscalated]      = useState(null);
  const [agentConnected, setAgentConnected] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  useEffect(() => {
    if (!convId) return;
    const es = new EventSource(`/api/chat/conversation/${convId}/stream`);
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.event === "agent:message") {
        setMessages(prev => [...prev, { role: "agent", content: data.content }]);
        setAgentConnected(true);
      }
    };
    return () => es.close();
  }, [convId]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput(""); setLoading(true);
    setMessages(prev => [...prev, { role: "user", content: text }]);
    const pid = Date.now();
    setMessages(prev => [...prev, { role: "assistant", content: "", streaming: true, id: pid }]);
    try {
      const url = `/api/chat/stream?message=${encodeURIComponent(text)}${convId ? "&conversation_id=" + convId : ""}`;
      const es  = new EventSource(url);
      let full  = "";
      es.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.event === "escalated") {
          setEscalated({ ticket_id: data.ticket_id, priority: data.priority || "MEDIUM" });
          es.close(); setLoading(false); return;
        }
        if (data.event === "token") {
          full += data.text;
          setMessages(prev => prev.map(m => m.id === pid ? { ...m, content: full } : m));
        }
        if (data.event === "done") {
          setMessages(prev => prev.map(m => m.id === pid ? { ...m, streaming: false, id: undefined } : m));
          if (data.conversation_id) setConvId(data.conversation_id);
          es.close(); setLoading(false);
        }
      };
      es.onerror = () => { es.close(); setLoading(false); };
    } catch { setLoading(false); }
  }, [input, loading, convId]);

  return (
    <div className="flex flex-col h-screen max-w-2xl mx-auto">
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-3">
        <div className="w-9 h-9 rounded-full bg-brand-500 flex items-center justify-center text-white font-bold text-sm">N</div>
        <div>
          <h1 className="font-semibold text-gray-900 text-sm">NexaAgent Support</h1>
          <p className="text-xs text-gray-500">{agentConnected ? "Human agent connected" : "AI-powered"}</p>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
          <span className="text-xs text-gray-500">Online</span>
        </div>
      </div>

      {escalated && (
        <div className="mx-4 mt-3 px-4 py-3 bg-blue-50 border border-blue-200 rounded-xl flex items-start gap-3">
          <AlertCircle className="text-blue-500 shrink-0 mt-0.5" size={16} />
          <div>
            <p className="text-sm font-medium text-blue-800">Connected to a human agent</p>
            <p className="text-xs text-blue-600 mt-0.5">
              Ticket #{escalated.ticket_id?.split("-")[0].toUpperCase()}
              &nbsp;- Expected: {WAIT[escalated.priority] || "soon"}
            </p>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.map((msg, i) => <Bubble key={i} msg={msg} />)}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-gray-100 bg-white px-4 py-3">
        <div className="flex gap-2 items-end">
          <textarea rows={1} value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="Type your message..."
            disabled={loading}
            className="flex-1 resize-none border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-gray-50 max-h-32"
          />
          <button onClick={send} disabled={loading || !input.trim()} className="btn-primary p-2.5 rounded-xl">
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
          </button>
        </div>
        <p className="text-center text-xs text-gray-400 mt-2">Powered by NexaAgent</p>
      </div>
    </div>
  );
}
