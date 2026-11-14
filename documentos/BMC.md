# LeakFinder Londrina — Business Model Canvas (BMC)

> Modelo de negócio para governo (B2G): o cliente é a prefeitura. Nada de venda para pessoas físicas.
> Valores de economia do protótipo são **simulados**. Não há preços definidos: dependem de um estudo de custos.

```
┌──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│ 8. Parcerias │ 7. Atividades│ 2. Proposta  │ 4. Relaciona-│ 1. Segmentos │
│              ├──────────────┤   de valor   │    mento     │  de clientes │
│              │ 6. Recursos  │              ├──────────────┤              │
│              │              │              │ 3. Canais    │              │
├──────────────┴──────────────┴───────┬──────┴──────────────┴──────────────┤
│ 9. Estrutura de custos              │ 5. Fontes de receita               │
└─────────────────────────────────────┴────────────────────────────────────┘
```

---

## Texto curto (para colar no Canva)

**🤝 Parcerias-chave**
- Prefeitura de Londrina (Educação, TI, Manutenção)
- Sanepar
- SENAI e universidades
- Fornecedores de câmeras e nuvem

**⚙️ Atividades-chave**
- Instalar câmeras nos hidrômetros
- Detectar vazamentos e gerar alertas
- Manter a plataforma
- Relatório mensal de economia

**🧰 Recursos-chave**
- Plataforma LeakFinder (painel + detecção)
- Câmeras ESP32-CAM com bateria e painel solar
- Histórico de consumo de cada unidade
- Equipe técnica

**💧 Proposta de valor**
- Vazamento detectado em ~1 hora, não na conta do mês
- Menos dinheiro público desperdiçado
- Escolas e CMEIs sem falta de água
- Sem obra e sem tomada: a câmera lê o hidrômetro existente
- Gestão com dados em tempo real

**💬 Relacionamento**
- Piloto em escolas e CMEIs
- Treinamento das equipes
- Relatório mensal de economia
- Suporte técnico

**📣 Canais**
- Painel web do gestor
- Programas de inovação da prefeitura
- Eventos e hackathons

**🏫 Segmentos de clientes**
- Prefeitura de Londrina
- Secretaria Municipal de Educação
- Equipes de manutenção e diretores
- Futuro: outras secretarias e municípios

**💸 Estrutura de custos**
- Câmeras, baterias, painéis solares e instalação
- Troca periódica de bateria
- Internet nas unidades
- Servidor e nuvem
- Equipe de desenvolvimento e suporte

**💰 Fontes de receita**
- Remuneração por % da economia comprovada
- A prefeitura só paga se economizar
- O sistema se paga com a água que deixa de vazar
- Economia financia a expansão para outros prédios

---

## Detalhes de cada bloco

### 1. Segmentos de clientes
- **Quem paga:** Prefeitura de Londrina, começando pela Secretaria Municipal de Educação (escolas e CMEIs).
- **Quem usa:** gestores e fiscais de contrato, equipe de manutenção, diretores das unidades.
- **Expansão:** fase 2 com outras secretarias (Saúde, Esportes, Cultura, Assistência Social); depois, outros municípios.

### 2. Proposta de valor
- Vazamento percebido em cerca de 1 hora, e não na conta do mês seguinte.
- Menos dinheiro público perdido: o painel mostra a perda de cada ocorrência.
- Escolas e CMEIs funcionando, sem aulas suspensas por falta de água.
- Sem obra e sem tomada: uma câmera de baixo custo, com bateria e painel solar, lê o hidrômetro que já existe.
- Gestão com dados: quanto, quando e onde cada unidade consome, com alertas e campo de operação.

### 3. Canais
- Painel web do gestor.
- Contratação pública: piloto via programas de inovação da prefeitura e, depois, modelos de compra de soluções
  inovadoras (ex.: Marco Legal das Startups, LC 182/2021). *Confirmar com a assessoria jurídica.*
- Hackathons e eventos de inovação.

### 4. Relacionamento
- Piloto em algumas unidades antes de expandir.
- Treinamento da manutenção e dos gestores.
- Relatório mensal de economia e ocorrências.
- Suporte técnico e manutenção das câmeras.

### 5. Fontes de receita (baseadas na economia)
- **Contrato de eficiência:** a remuneração é uma porcentagem da economia comprovada na conta de água.
  A Lei 14.133/2021 (Nova Lei de Licitações) prevê o contrato de eficiência. *Confirmar com a assessoria jurídica.*
- **Taxa de implantação reduzida**, só para a instalação das câmeras.
- **Expansão financiada pela economia** das primeiras unidades.

**Como a economia é medida:**
1. Antes de começar, o consumo médio de cada unidade vira a **linha de base**.
2. A cada mês: vazamentos evitados (água que vazaria até a próxima conta − água que vazou até o conserto)
   e redução de consumo (linha de base − consumo atual).
3. Litros economizados × tarifa da Sanepar = economia em R$.
4. Relatório mensal com cada ocorrência e a foto do hidrômetro como prova.

*Exemplo simulado:* uma torneira aberta de madrugada a 7 L/min perderia ~302 mil litros até a conta do mês;
com o LeakFinder, perde ~630 litros.

### 6. Recursos-chave
- Plataforma de software (leituras, detecção, painel, campo de operação).
- Câmeras ESP32-CAM com bateria e painel solar, com a leitura dos dígitos do hidrômetro.
- Histórico de consumo de cada unidade.
- Equipe técnica.

### 7. Atividades-chave
- Desenvolver e manter a plataforma.
- Instalar e calibrar as câmeras; trocar baterias.
- Monitorar os alertas e melhorar a detecção.
- Gerar os relatórios de economia.

### 8. Parcerias-chave
- Prefeitura (Educação, TI municipal, Manutenção).
- Sanepar (dados e, na visão municipal, perdas na rede).
- SENAI e universidades de Londrina (pesquisa, estágios, manutenção).
- Fornecedores de hardware e de nuvem.

### 9. Estrutura de custos
- Por unidade: câmera, bateria, painel solar, caixa de proteção e instalação.
- Troca periódica de bateria.
- Conectividade (forma ainda em aberto — ver [DECISOES_E_PERGUNTAS.md](DECISOES_E_PERGUNTAS.md)).
- Servidor e nuvem.
- Equipe de desenvolvimento, suporte e visitas de manutenção.
