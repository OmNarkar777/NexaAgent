import axios from "axios";
const api = axios.create({ baseURL: "/api" });
api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem("nexaagent_token");
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});
api.interceptors.response.use(
  (r) => r,
  (err) => { if (err.response?.status === 401) localStorage.removeItem("nexaagent_token"); return Promise.reject(err); }
);
export default api;