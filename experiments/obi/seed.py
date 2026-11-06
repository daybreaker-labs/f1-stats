#!/usr/bin/env python3
"""Deterministic synthetic /home fixture for F1 Stats (no production data).
  seed.py <bcrypt-hash> > seed.sql   then load into the migrated fixture DB.
Two users share password `home-fixture-password`:
  heavy  home-fixture@example.test   250 seasons x 20 races x 20 drivers = 5000 races, 100000 results, 250 titles
  light  home-no-titles@example.test 25 seasons x 20 races x 20 drivers = 500 races, 10000 results, no titles
The shapes follow the FOUND-306 offline fixtures (5000 races / 250 titles and 500 races / 0 titles).
Every driver is named `Fixture Pilot NN`, which measure_exec.py checks for in the rendered page."""
import sys, random
pw = sys.argv[1]
HEAVY_SEASONS, LIGHT_SEASONS, RACES_PER_SEASON, DRIVERS = 250, 25, 20, 20
rnd = random.Random(339)
out = []
def ins(table, cols, rows):
    for i in range(0, len(rows), 1000):
        vals = ','.join('(' + ','.join('NULL' if v is None else str(v) if isinstance(v, (int, float)) else "'" + v.replace("'", "''") + "'" for v in r) + ')' for r in rows[i:i + 1000])
        out.append(f"INSERT INTO {table} ({','.join(cols)}) VALUES {vals};")
ids = {k: 0 for k in ('pais', 'equipe', 'piloto', 'pista', 'ano', 'pe', 'temp', 'corrida', 'res', 'titulo')}
def nid(k): ids[k] += 1; return ids[k]
# continentes is filled by the migrations; id 1 exists.
def user(uid, name, email, seasons, races_per_season, titles):
    ins('users', ['id', 'name', 'email', 'password', 'created_at', 'updated_at'], [(uid, name, email, pw, '2026-01-01 00:00:00', '2026-01-01 00:00:00')])
    pais = nid('pais'); ins('paises', ['id', 'des_nome', 'continente_id', 'imagem', 'user_id'], [(pais, 'Fixtureland', 1, None, uid)])
    anos = [nid('ano') for _ in range(seasons)]
    ins('anos', ['id', 'ano', 'user_id', 'flg_ativo'], [(a, str(1800 + j), uid, 'S') for j, a in enumerate(anos)])
    equipes = [nid('equipe') for _ in range(DRIVERS // 2)]
    ins('equipes', ['id', 'nome', 'imagem', 'des_cor', 'pais_id', 'user_id', 'flg_ativo'], [(e, f'Fixture Team {j + 1:02d}', None, '#000000', pais, uid, 'S') for j, e in enumerate(equipes)])
    pilotos = [nid('piloto') for _ in range(DRIVERS)]
    ins('pilotos', ['id', 'nome', 'sobrenome', 'imagem', 'pais_id', 'user_id', 'flg_ativo'], [(p, 'Fixture', f'Pilot {j + 1:02d}', None, pais, uid, 'S') for j, p in enumerate(pilotos)])
    pistas = [nid('pista') for _ in range(10)]
    ins('pistas', ['id', 'nome', 'pais_id', 'user_id', 'flg_ativo', 'tamanho_km', 'qtd_voltas'], [(t, f'Fixture Track {j + 1:02d}', pais, uid, 'S', 5, 50) for j, t in enumerate(pistas)])
    pes, temps, corridas, res, tits = [], [], [], [], []
    for s, ano in enumerate(anos):
        pe = [(nid('pe'), pilotos[d], equipes[d // 2], uid, ano, 'S') for d in range(DRIVERS)]; pes += pe
        t = nid('temp'); temps.append((t, f'{1800 + s} Season', ano, uid, 'S', str(1800 + s)))
        for r in range(races_per_season):
            c = nid('corrida'); corridas.append((c, t, pistas[r % len(pistas)], r + 1, 1, 'N', uid))
            grid = list(range(1, DRIVERS + 1)); rnd.shuffle(grid); finish = list(range(1, DRIVERS + 1)); rnd.shuffle(finish)
            for d in range(DRIVERS):
                ab = 'S' if finish[d] > 18 else 'N'
                res.append((nid('res'), c, pe[d][0], grid[d], finish[d], float(max(0, 26 - finish[d])), uid, 0, 0, 0, ab))
        if titles: tits.append((nid('titulo'), t, pe[0][0], pe[0][2], uid))
    ins('piloto_equipes', ['id', 'piloto_id', 'equipe_id', 'user_id', 'ano_id', 'flg_ativo'], pes)
    ins('temporadas', ['id', 'des_temporada', 'ano_id', 'user_id', 'flg_finalizada', 'referencia'], temps)
    ins('corridas', ['id', 'temporada_id', 'pista_id', 'ordem', 'exibir_resultado', 'flg_sprint', 'user_id'], corridas)
    ins('resultados', ['id', 'corrida_id', 'pilotoEquipe_id', 'largada', 'chegada', 'pontuacao', 'user_id', 'pontuacao_classica', 'pontuacao_personalizada', 'pontuacao_invertida', 'flg_abandono'], res)
    if tits: ins('titulos', ['id', 'temporada_id', 'pilotoEquipe_id', 'equipe_id', 'user_id'], tits)
user(1, 'Heavy Fixture', 'home-fixture@example.test', HEAVY_SEASONS, RACES_PER_SEASON, True)
user(2, 'Light Fixture', 'home-no-titles@example.test', LIGHT_SEASONS, RACES_PER_SEASON, False)
print('SET FOREIGN_KEY_CHECKS=0;'); print('\n'.join(out)); print('SET FOREIGN_KEY_CHECKS=1;')
