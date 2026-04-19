import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from "recharts";
import { Zap, Clock, ShieldAlert, Users, BarChart2, Activity } from "lucide-react";
import api from "../api/client";

const COLORS = ["#0ea5e9","#8b5cf6","#f59e0b","#10b981","#ef4444","#6366f1","#ec4899"];
const pct = n => (n * 100).toFixed(1) + "%";
const ms  = n => n >= 1000 ? (n / 1000).toFixed(1) + "s" : Math.round(n) + "ms";

function KPI({ title, value, sub, icon: Icon, warn }) {
  return (
    <div className="card flex items-start gap-4">
      <div className={`p-2.5 rounded-xl shrink-0 ${warn ? "bg-red-50" : "bg-brand-50"}`}>
        <Icon size={20} className={warn ? "text-red-500" : "text-brand-500"} />
      </div>
      <div>
        <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{title}</p>
        <p className="text-2xl font-bold text-gray-900 mt-0.5">{value}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

export default function OpsDashboard() {
  const [win, setWin] = useState("24h");
  const opts = { refetchInterval: 30000 };
  const { data: ov } = useQuery({ queryKey:["ov",win], queryFn:() => api.get(`/analytics/overview?window=${win}`).then(r=>r.data), ...opts });
  const { data: ib } = useQuery({ queryKey:["ib",win], queryFn:() => api.get(`/analytics/intent_breakdown?window=${win}`).then(r=>r.data), ...opts });
  const { data: st } = useQuery({ queryKey:["st",win], queryFn:() => api.get(`/analytics/sentiment_trend?window=${win}`).then(r=>r.data), ...opts });
  const { data: ap } = useQuery({ queryKey:["ap",win], queryFn:() => api.get(`/analytics/agent_performance?window=${win}`).then(r=>r.data), ...opts });

  const stData = (st || []).map(d => ({
    time: new Date(d.hour).toLocaleTimeString([], { hour:"2-digit", minute:"2-digit" }),
    sentiment: d.avg_sentiment,
    convs: d.conversation_count,
  }));

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b px-8 py-4 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <BarChart2 size={20} className="text-brand-500" />
          <h1 className="font-bold text-lg">Ops Dashboard</h1>
        </div>
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
          {["24h","7d","30d"].map(w => (
            <button key={w} onClick={() => setWin(w)}
              className={[
                "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                win === w ? "bg-white shadow-sm text-gray-900" : "text-gray-500 hover:text-gray-700"
              ].join(" ")}>
              {w}
            </button>
          ))}
        </div>
      </div>

      <div className="px-8 py-6 space-y-5">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KPI title="Total Conversations" value={ov?.total_conversations ?? "-"} icon={Activity} />
          <KPI title="Escalation Rate" value={ov ? pct(ov.escalation_rate) : "-"} icon={Users}
               warn={ov?.escalation_rate > 0.25} />
          <KPI title="Avg Response Time" value={ov ? ms(ov.avg_response_time_ms) : "-"} icon={Zap}
               sub={ov?.cache_hit_rate ? pct(ov.cache_hit_rate) + " cached" : ""} />
          <KPI title="SLA Breaches" value={ov?.sla_breach_count ?? "-"} icon={ShieldAlert}
               warn={(ov?.sla_breach_count || 0) > 0} />
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KPI title="AI Resolved"        value={ov?.ai_resolved ?? "-"}                      icon={Zap} />
          <KPI title="Escalated to Human" value={ov?.escalated_to_human ?? "-"}               icon={Users} />
          <KPI title="Cache Hit Rate"     value={ov ? pct(ov.cache_hit_rate) : "-"}           icon={Activity} sub="Sub-100ms cached" />
          <KPI title="Avg Resolution"     value={ov ? ov.avg_resolution_time_minutes + "m" : "-"} icon={Clock} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="card">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Activity size={15} className="text-brand-500" /> Sentiment Trend
            </h3>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={stData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                <YAxis domain={[-1, 1]} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="sentiment" stroke="#0ea5e9" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="card">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <BarChart2 size={15} className="text-brand-500" /> Intent Breakdown
            </h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={ib || []} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="intent" tick={{ fontSize: 10 }} width={120} />
                <Tooltip />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {(ib || []).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <Users size={15} className="text-brand-500" /> Agent Performance
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  {["Agent","Active","Resolved","Avg Resolution","SLA Breaches"].map(h => (
                    <th key={h} className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {(ap || []).map(a => (
                  <tr key={a.agent_id} className="hover:bg-gray-50">
                    <td className="py-3 px-4 font-medium">{a.name}</td>
                    <td className="py-3 px-4">
                      <span className={`badge ${a.current_ticket_count >= 8 ? "bg-red-100 text-red-700" : "bg-gray-100 text-gray-700"}`}>
                        {a.current_ticket_count}
                      </span>
                    </td>
                    <td className="py-3 px-4">{a.tickets_resolved}</td>
                    <td className="py-3 px-4">{a.avg_resolution_minutes}m</td>
                    <td className="py-3 px-4">
                      <span className={`badge ${a.sla_breach_count > 0 ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700"}`}>
                        {a.sla_breach_count}
                      </span>
                    </td>
                  </tr>
                ))}
                {!(ap?.length) && (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-gray-400 text-sm">No data for this period</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
