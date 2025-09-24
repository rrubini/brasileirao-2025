import json
import sys
from typing import List, Dict

SEASON_GAMES = 38
SHRINK_K = 6  # força da regressão à média (puxa ppg para média da liga)

def load_table_from_json(path: str | None) -> List[Dict]:
    """
    Lê o JSON no formato que você enviou.
    Se path for None, tenta ler da stdin (permite: type tabela.json | python script.py).
    Retorna uma lista de times com campos necessários mapeados para nomes padronizados.
    """
    if path:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    rows = []
    for t in data:
        # Campos de entrada (conforme seu JSON)
        nome = t["nome_popular"]
        pts  = int(t["pontos"])
        j    = int(t["jogos"])
        gp   = int(t.get("gols_pro", 0))
        gc   = int(t.get("gols_contra", 0))
        sg   = int(t.get("saldo_gols", gp - gc))
        # Vitórias (primeiro critério de desempate)
        w    = int(t.get("vitorias", t.get("v", t.get("wins", 0))))

        rows.append({
            "team": nome,
            "pts": pts,
            "j": j,
            "gp": gp,
            "gc": gc,
            "sg": sg,
            "w": w,
        })
    if len(rows) != 20:
        # Não é obrigatório ter 20, mas no BR comum esperamos 20
        # Mantemos como aviso leve.
        print(f"[AVISO] Tabela com {len(rows)} times (esperado: 20).", file=sys.stderr)
    return rows

def project_final_points(rows: List[Dict]) -> List[Dict]:
    # Média da liga em pontos por jogo até agora
    total_pts = sum(r["pts"] for r in rows if r["j"] > 0)
    total_j   = sum(r["j"]  for r in rows if r["j"] > 0)
    league_avg_ppg = (total_pts / total_j) if total_j > 0 else 0.0

    # Médias da liga de gols pró e contra por jogo (por time)
    total_gf = sum(r["gp"] for r in rows if r["j"] > 0)
    total_ga = sum(r["gc"] for r in rows if r["j"] > 0)
    league_avg_gfpg = (total_gf / total_j) if total_j > 0 else 0.0
    league_avg_gapg = (total_ga / total_j) if total_j > 0 else 0.0

    # Média de vitórias por jogo na liga (por time)
    total_w = sum(r.get("w", 0) for r in rows if r["j"] > 0)
    league_avg_wpg = (total_w / total_j) if total_j > 0 else 0.0

    proj = []
    for r in rows:
        pts, j = r["pts"], r["j"]
        gp, gc = r["gp"], r["gc"]
        w      = r.get("w", 0)
        remaining = max(0, SEASON_GAMES - j)
        if j + SHRINK_K > 0:
            reg_ppg  = (pts + SHRINK_K * league_avg_ppg)  / (j + SHRINK_K)
            reg_gfpg = (gp  + SHRINK_K * league_avg_gfpg) / (j + SHRINK_K)
            reg_gapg = (gc  + SHRINK_K * league_avg_gapg) / (j + SHRINK_K)
            reg_wpg  = (w   + SHRINK_K * league_avg_wpg)  / (j + SHRINK_K)
        else:
            reg_ppg, reg_gfpg, reg_gapg, reg_wpg = league_avg_ppg, league_avg_gfpg, league_avg_gapg, league_avg_wpg

        exp_future = reg_ppg * remaining
        final_pts  = pts + exp_future

        # Projeção de gols pró/contra e saldo
        exp_future_gf = reg_gfpg * remaining
        exp_future_ga = reg_gapg * remaining
        final_gp = gp + exp_future_gf
        final_gc = gc + exp_future_ga
        final_sg = final_gp - final_gc

        # Projeção de vitórias
        final_w = w + reg_wpg * remaining

        proj.append({**r, "final_pts": final_pts, "final_gp": final_gp, "final_gc": final_gc, "final_sg": final_sg, "final_w": final_w})

    # Ordenação (critérios oficiais): pontos, vitórias, saldo, gols pró
    proj.sort(key=lambda x: (
        -x["final_pts"],
        -x.get("final_w", 0),
        -x.get("final_sg", x.get("sg", 0)),
        -x.get("final_gp", x.get("gp", 0)),
    ))
    return proj

def print_projection(proj: List[Dict]):
    print("== PROJEÇÃO DE TÍTULO E REBAIXAMENTO ==")
    for i, r in enumerate(proj, start=1):
        print(f"{i:2d}. {r['team']:<20} {r['final_pts']:.0f} pts (V proj: {r.get('final_w', 0):.0f}, SG proj: {r.get('final_sg', 0):.0f}) (pts atuais: {r['pts']}, jogos atuais: {r['j']})")

    # 4 rebaixados: posições 17-20
    relegated = [r["team"] for r in proj[-4:]]
    print("\nRebaixados projetados:", ", ".join(relegated))

def save_html_projection(proj: List[Dict], output_path: str = "projecao_brasileirao.html"):
    """Gera um HTML com a projeção em formato de tabela."""
    rows_html = []
    for i, r in enumerate(proj, start=1):
        cls = "relegated" if i >= 17 else ""
        rows_html.append(
            f"<tr class='{cls}'>"
            f"<td>{i}</td>"
            f"<td>{r['team']}</td>"
            f"<td>{r['final_pts']:.0f}</td>"
            f"<td>{r.get('final_w', 0):.0f}</td>"
            f"<td>{r['pts']}</td>"
            f"<td>{r['j']}</td>"
            f"<td>{r.get('final_gp', r['gp']):.0f}</td>"
            f"<td>{r.get('final_gc', r['gc']):.0f}</td>"
            f"<td>{r.get('final_sg', r.get('sg', 0)):.0f}</td>"
            f"</tr>"
        )

    html = f"""<!doctype html>
<html lang=\"pt-br\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Projeção Brasileirão</title>
  <style>
    :root {{ --bg:#ffffff; --fg:#1b1f23; --muted:#6a737d; --line:#eaecef; --zebra:#fafbfc; --accent:#0366d6; --bad:#b00020; }}
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Arial, \"Apple Color Emoji\", \"Segoe UI Emoji\"; background:var(--bg); color:var(--fg); margin:0; padding:32px 16px; }}
    h1 {{ text-align:center; font-size:1.4rem; margin:0 0 16px; }}
    .container {{ max-width: 1000px; margin: 0 auto; }}
    table {{ width:100%; border-collapse: collapse; background:#fff; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
    thead th {{ background: var(--zebra); text-align:left; font-weight:600; font-size:0.9rem; padding:10px 12px; border-bottom:1px solid var(--line); }}
    tbody td {{ padding:10px 12px; border-bottom:1px solid var(--line); font-size:0.92rem; }}
    tbody tr:nth-child(even) {{ background: var(--zebra); }}
    tbody tr.relegated td {{ color: var(--bad); font-weight:600; }}
    .legend {{ margin-top:10px; color:var(--muted); font-size:0.85rem; }}
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>Projeção de Tabela — Brasileirão</h1>
    <table>
      <thead>
        <tr>
          <th>Pos</th>
          <th>Time</th>
          <th>Pts proj</th>
          <th>V proj</th>
          <th>Pts</th>
          <th>J</th>
          <th>GP proj</th>
          <th>GC proj</th>
          <th>SG proj</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows_html)}
      </tbody>
    </table>
    <div class=\"legend\">Linhas em vermelho: zona de rebaixamento (17º a 20º). Desempate: vitórias, saldo, gols pró.</div>
  </div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[OK] HTML salvo em: {output_path}")

def main():
    """
    Uso:
      python brasileiro_from_json.py tabela.json [saida.html]
      # ou lendo da stdin e informando só a saída:
      type tabela.json | python brasileiro_from_json.py saida.html
    """
    # Interpretação flexível dos argumentos para permitir stdin
    json_arg = sys.argv[1] if len(sys.argv) > 1 else None
    out_arg  = sys.argv[2] if len(sys.argv) > 2 else None

    if json_arg and json_arg.lower().endswith((".html", ".htm")) and out_arg is None:
        # Caso: lendo da stdin e o único arg é o caminho do HTML
        path = None
        out_path = json_arg
    else:
        path = json_arg
        out_path = out_arg or "projecao_brasileirao.html"

    rows = load_table_from_json(path)
    proj = project_final_points(rows)
    print_projection(proj)
    save_html_projection(proj, out_path)

if __name__ == "__main__":
    main()
