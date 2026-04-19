import React, { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Send, CheckCircle, RefreshCw, Inbox, User, Clock } from "lucide-react";
import api from "../api/client";
import { useSSE } from "../hooks/useSSE";

const P_STYLE = {
  CRITICAL: "bg-red-100 text-red-700 border-red-200",
  HIGH:     "bg-orange-100 text-orange-700 border-orange-200",
  MEDIUM:   "bg-yellow-100 text-yellow-700 border-yellow-200",
  LOW:      "bg-blue-100 text-blue-700 border-blue-200",
};
const S_DOT = {
  FRUSTRATED: "bg-red-500", NEGATIVE: "bg-orange-400",
  NEUTRAL: "bg-gray-400",  POSITIVE: "bg-green-400"
};

export default function AgentDashboard() {
  const qc = useQueryClient();
  const [active,      setActive]      = useState(null);
  const [conversation,setConversation]= useState([]);
  const [reply,       setReply]       = useState("");
  const [notes,       setNotes]       = useState("");
  const [showResolve, setShowResolve] = useState(false);

  const { data: queueData, refetch } = useQuery({
    queryKey: ["agent-queue"],
    queryFn:  () => api.get("/agent/queue").then(r => r.data),
    refetchInterval: 15000,
  });

  useSSE("/api/agent/queue/stream", useCallback((e) => {
    const EVENTS = ["ticket:new","ticket:claimed","ticket:resolved","ticket:transferred"];
    if (EVENTS.includes(e.event)) qc.invalidateQueries(["agent-queue"]);
  }, [qc]));

  const claimMut = useMutation({
    mutationFn: () => api.post("/agent/queue/claim").then(r => r.data),
    onSuccess: (d) => { setActive(d.ticket); setConversation(d.conversation); refetch(); },
  });
  const sendMut = useMutation({
    mutationFn: (c) => api.post(`/agent/tickets/${active.ticket_id}/message`, { content: c }).then(r => r.data),
    onSuccess: () => {
      setConversation(p => [...p, { role:"agent", content:reply, created_at: new Date().toISOString() }]);
      setReply("");
    },
  });
  const resolveMut = useMutation({
    mutationFn: () => api.post(`/agent/tickets/${active.ticket_id}/resolve`,
      { resolution_notes: notes, satisfaction_prompted: true }).then(r => r.data),
    onSuccess: () => { setActive(null); setConversation([]); setNotes(""); setShowResolve(false); refetch(); },
  });

  const depth   = queueData?.depth   || {};
  const tickets = queueData?.tickets || [];

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <aside className="w-80 bg-white border-r border-gray-100 flex flex-col">
        <div className="px-5 py-4 border-b border-gray-100">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-bold text-gray-900">Queue</h2>
            <button onClick={refetch} className="p-1.5 rounded-lg hover:bg-gray-100"><RefreshCw size={13} /></button>
          </div>
          <div className="grid grid-cols-4 gap-1 mb-3">
            {["CRITICAL","HIGH","MEDIUM","LOW"].map(p => (
              <div key={p} className={`flex flex-col items-center p-2 rounded-xl border text-center ${P_STYLE[p]}`}>
                <span className="text-xl font-bold">{depth[p] || 0}</span>
                <span className="text-xs mt-0.5">{p.slice(0,4)}</span>
              </div>
            ))}
          </div>
          <button onClick={() => claimMut.mutate()} disabled={claimMut.isPending || !tickets.length}
            className="btn-primary w-full flex items-center justify-center gap-2">
            <Inbox size={15} />{claimMut.isPending ? "Claiming..." : "Claim Next"}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {tickets.map(t => (
            <div key={t.ticket_id}
              onClick={() => { setActive(t); setConversation(t.conversation_preview || []); }}
              className={[
                "p-3 rounded-xl border cursor-pointer hover:shadow-sm transition-all",
                active?.ticket_id === t.ticket_id ? "ring-2 ring-brand-500" : "border-gray-100"
              ].join(" ")}>
              <div className="flex items-center gap-2 mb-1">
                <span className={`badge border ${P_STYLE[t.priority]}`}>{t.priority}</span>
                <span className="text-xs font-mono text-gray-400 ml-auto">
                  #{t.ticket_id?.split("-")[0].toUpperCase()}
                </span>
              </div>
              <p className="text-xs text-gray-600 line-clamp-2">{t.escalation_reason}</p>
              <p className="text-xs text-gray-400 mt-1 flex items-center gap-1">
                <Clock size={9} />{new Date(t.created_at).toLocaleTimeString()}
              </p>
            </div>
          ))}
          {!tickets.length && (
            <div className="text-center py-10 text-gray-400">
              <Inbox size={28} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">Queue empty</p>
            </div>
          )}
        </div>
      </aside>

      <main className="flex-1 flex flex-col overflow-hidden">
        {!active ? (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <div className="text-center">
              <User size={44} className="mx-auto mb-2 opacity-30" />
              <p className="font-medium">No active ticket</p>
              <p className="text-sm">Claim one from the queue</p>
            </div>
          </div>
        ) : (
          <>
            <div className="bg-white border-b px-6 py-4 flex items-center gap-3">
              <span className={`badge border ${P_STYLE[active.priority]}`}>{active.priority}</span>
              <span className="font-mono text-sm font-medium">
                #{active.ticket_id?.split("-")[0].toUpperCase()}
              </span>
              <p className="text-xs text-gray-500">{active.escalation_reason}</p>
              <button onClick={() => setShowResolve(true)}
                className="ml-auto flex items-center gap-1.5 px-3 py-1.5 bg-green-500 hover:bg-green-600 text-white text-sm font-medium rounded-lg">
                <CheckCircle size={13} /> Resolve
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-2">
              {conversation.map((m, i) => (
                <div key={i} className={[
                  "rounded-xl p-3 text-sm",
                  m.role === "user"      ? "bg-gray-100" :
                  m.role === "agent"     ? "bg-green-50 border border-green-200" :
                                           "bg-brand-50 border border-brand-100"
                ].join(" ")}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-xs uppercase text-gray-500">{m.role}</span>
                    {m.sentiment && <span className={`w-2 h-2 rounded-full ${S_DOT[m.sentiment] || "bg-gray-400"}`} />}
                    {m.intent && <span className="text-xs italic text-gray-400">{m.intent}</span>}
                    <span className="ml-auto text-xs text-gray-400">
                      {m.created_at ? new Date(m.created_at).toLocaleTimeString() : ""}
                    </span>
                  </div>
                  <p className="text-gray-800">{m.content}</p>
                </div>
              ))}
            </div>

            {showResolve && (
              <div className="absolute inset-0 bg-black/40 flex items-center justify-center z-50">
                <div className="card w-full max-w-md mx-4">
                  <h3 className="font-semibold text-lg mb-3">Resolve Ticket</h3>
                  <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={4}
                    placeholder="Resolution notes (min 10 chars)..."
                    className="w-full border border-gray-200 rounded-xl p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-500 mb-3" />
                  <div className="flex gap-2 justify-end">
                    <button onClick={() => setShowResolve(false)} className="btn-ghost">Cancel</button>
                    <button onClick={() => resolveMut.mutate()} disabled={notes.length < 10 || resolveMut.isPending}
                      className="btn-primary flex items-center gap-2">
                      <CheckCircle size={13} />{resolveMut.isPending ? "Saving..." : "Confirm"}
                    </button>
                  </div>
                </div>
              </div>
            )}

            <div className="bg-white border-t px-5 py-3">
              <div className="flex gap-2">
                <textarea rows={2} value={reply} onChange={e => setReply(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      if (reply.trim()) sendMut.mutate(reply.trim());
                    }
                  }}
                  placeholder="Reply to customer..."
                  className="flex-1 border border-gray-200 rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-500" />
                <button onClick={() => reply.trim() && sendMut.mutate(reply.trim())}
                  disabled={!reply.trim() || sendMut.isPending}
                  className="btn-primary px-4 rounded-xl">
                  <Send size={16} />
                </button>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
