/* ===== Temas de Postuladorsito: se aplican antes de pintar la página (sin parpadeo) ===== */
window.TEMAS={
 vice:{nombre:"Miami Vice City Neón",desc:"Rosa, cian y violeta de noche",v:{"--bg-primary":"#07040f","--bg-card":"#1c1236","--accent-primary":"#ff2e97","--accent-secondary":"#22e4ff","--accent-tertiary":"#9b5cff","--text-primary":"#f5f0fb","--on-accent":"#ffffff","--ok":"#35e8a8","--warn":"#ffb547","--danger":"#ff5a76","--glow":"1","--glass":".55","--borde":".10"}},
 cyberpunk:{nombre:"Cyberpunk Amarillo/Cian",desc:"Amarillo eléctrico sobre negro",v:{"--bg-primary":"#0a0a0c","--bg-card":"#17170f","--accent-primary":"#fcee0a","--accent-secondary":"#00f0ff","--accent-tertiary":"#ff003c","--text-primary":"#f4f4e8","--on-accent":"#0a0a0c","--ok":"#3dff9e","--warn":"#ffb000","--danger":"#ff3355","--glow":"1.1","--glass":".7","--borde":".14"}},
 matrix:{nombre:"Matrix Verde Terminal",desc:"Fósforo verde de consola",v:{"--bg-primary":"#010803","--bg-card":"#06160b","--accent-primary":"#00ff66","--accent-secondary":"#7dffb0","--accent-tertiary":"#00b347","--text-primary":"#c9ffd9","--on-accent":"#011a08","--ok":"#00ff66","--warn":"#d4ff3d","--danger":"#ff5c5c","--glow":"1.2","--glass":".75","--borde":".14"}},
 synthwave:{nombre:"Synthwave Violeta/Naranja",desc:"Atardecer retro de los 80",v:{"--bg-primary":"#140629","--bg-card":"#26104d","--accent-primary":"#ff7a18","--accent-secondary":"#ff2e97","--accent-tertiary":"#b026ff","--text-primary":"#fdf0ff","--on-accent":"#1a0526","--ok":"#3ef0b0","--warn":"#ffd23f","--danger":"#ff4f6d","--glow":"1.1","--glass":".6","--borde":".12"}},
 minimal:{nombre:"Blanco Minimalista",desc:"Claro, limpio y sin brillos",claro:true,v:{"--bg-primary":"#f5f5f3","--bg-card":"#ffffff","--accent-primary":"#2f6fed","--accent-secondary":"#0e9f6e","--accent-tertiary":"#6d4aff","--text-primary":"#18181b","--on-accent":"#ffffff","--ok":"#0e9f6e","--warn":"#b45309","--danger":"#dc2626","--glow":".12","--glass":".96","--borde":".12"}},
 ejecutivo:{nombre:"Azul Ejecutivo",desc:"Sobrio, para trabajar tranquilo",v:{"--bg-primary":"#0a1424","--bg-card":"#13233b","--accent-primary":"#3b82f6","--accent-secondary":"#7cc4ff","--accent-tertiary":"#6366f1","--text-primary":"#e9eff8","--on-accent":"#ffffff","--ok":"#34d399","--warn":"#fbbf24","--danger":"#f87171","--glow":".35","--glass":".8","--borde":".12"}},
 carmesi:{nombre:"Rojo Carmesí Oscuro",desc:"Rojo profundo y elegante",v:{"--bg-primary":"#0d0406","--bg-card":"#1f0a10","--accent-primary":"#e11d48","--accent-secondary":"#fb7185","--accent-tertiary":"#be123c","--text-primary":"#fdeef1","--on-accent":"#ffffff","--ok":"#4ade80","--warn":"#fbbf24","--danger":"#ff6b81","--glow":".8","--glass":".65","--borde":".12"}},
 esmeralda:{nombre:"Esmeralda Nocturno",desc:"Verdes profundos y aguamarina",v:{"--bg-primary":"#03110c","--bg-card":"#0b2219","--accent-primary":"#10b981","--accent-secondary":"#5eead4","--accent-tertiary":"#22c55e","--text-primary":"#e7fbf3","--on-accent":"#022016","--ok":"#34d399","--warn":"#fcd34d","--danger":"#fb7185","--glow":".7","--glass":".65","--borde":".12"}},
 dorado:{nombre:"Dorado & Negro",desc:"Lujo discreto",v:{"--bg-primary":"#090806","--bg-card":"#18150d","--accent-primary":"#d4af37","--accent-secondary":"#f3d98b","--accent-tertiary":"#b8860b","--text-primary":"#f7f0dc","--on-accent":"#1a1405","--ok":"#9fd77a","--warn":"#f0b44c","--danger":"#e3655b","--glow":".6","--glass":".75","--borde":".14"}},
 pastel:{nombre:"Pastel Suave",desc:"Rosa y celeste, tono amable",claro:true,v:{"--bg-primary":"#fbf6fa","--bg-card":"#ffffff","--accent-primary":"#e0609e","--accent-secondary":"#3f9fd1","--accent-tertiary":"#9b7fd9","--text-primary":"#3a3242","--on-accent":"#ffffff","--ok":"#2f9e72","--warn":"#c27a12","--danger":"#d64560","--glow":".3","--glass":".92","--borde":".11"}},
 lavanda:{nombre:"Lavanda & Menta",desc:"Fresco y luminoso",claro:true,v:{"--bg-primary":"#f2effa","--bg-card":"#ffffff","--accent-primary":"#7c4dff","--accent-secondary":"#14b8a6","--accent-tertiary":"#a78bfa","--text-primary":"#28223d","--on-accent":"#ffffff","--ok":"#0f9f8c","--warn":"#b7791f","--danger":"#d9455f","--glow":".3","--glass":".92","--borde":".12"}},
 contraste:{nombre:"Alto Contraste",desc:"Máxima legibilidad",v:{"--bg-primary":"#000000","--bg-card":"#000000","--accent-primary":"#ffff00","--accent-secondary":"#00ffff","--accent-tertiary":"#ffffff","--text-primary":"#ffffff","--on-accent":"#000000","--ok":"#00ff7f","--warn":"#ffbf00","--danger":"#ff4d4d","--glow":"0","--glass":"1","--borde":".5"}}
};
window.TEMA_DEFECTO="vice";
window.CLAVE_TEMA="postuladorsito_apariencia";
window.aplicarTema=function(id,custom){
  const t=TEMAS[id]||TEMAS[TEMA_DEFECTO], r=document.documentElement.style;
  const v=Object.assign({},t.v,custom||{});
  for(const k in v) r.setProperty(k,v[k]);
  const claro=custom&&custom["--bg-primary"]?esClaro(v["--bg-primary"]):!!t.claro;
  r.setProperty("color-scheme",claro?"light":"dark");
  document.documentElement.dataset.claro=claro?"1":"";
  return v;
};
window.esClaro=function(hex){const h=String(hex||"#000").replace("#","");const n=parseInt(h.length===3?h.split("").map(c=>c+c).join(""):h,16);
  const r=(n>>16)&255,g=(n>>8)&255,b=n&255;return (0.2126*r+0.7152*g+0.0722*b)/255>0.6;};
try{const g=JSON.parse(localStorage.getItem(CLAVE_TEMA)||"null");if(g)aplicarTema(g.tema,g.custom);}catch(e){}
