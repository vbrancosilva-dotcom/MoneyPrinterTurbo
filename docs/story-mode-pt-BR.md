# Modo História Cinematográfica

Este modo cria dois vídeos verticais completos a partir da mesma história:

- português do Brasil;
- inglês;
- as mesmas imagens e cenas nas duas versões;
- narração gratuita com Edge TTS;
- legendas e montagem pelo MoneyPrinterTurbo;
- imagens locais pelo Stable Diffusion Forge;
- adaptação, tradução e prompts locais pelo Ollama.

## Requisitos

O MoneyPrinterTurbo deve estar instalado normalmente com `uv sync --frozen`.

Instale o Ollama e baixe um modelo pequeno:

```powershell
ollama pull qwen2.5:3b
```

Instale o Stable Diffusion WebUI Forge e use um checkpoint SD 1.5. Em uma placa
com até 4 GB de VRAM, inicie o Forge com:

```text
--api --lowvram
```

O endereço padrão do Ollama é `http://127.0.0.1:11434` e o do Forge é
`http://127.0.0.1:7860`.

## Iniciar no Windows

Na raiz do projeto, execute:

```powershell
.\story_webui.bat
```

Abra `http://127.0.0.1:8502` se o navegador não abrir automaticamente.

## Fluxo

1. Informe o título e o idioma original.
2. Cole uma história própria ou que você tenha autorização para reutilizar.
3. Descreva os personagens sempre com os mesmos traços, roupas e cores.
4. Mantenha habilitada a adaptação para publicação se o texto tiver palavrões ou
   conteúdo sexual explícito.
5. Teste as conexões locais.
6. Gere a história.

O aplicativo divide o texto sem reordená-lo, traduz cada cena, cria um prompt
visual em inglês, gera uma imagem vertical por cena e monta as versões em português
e inglês. Histórias longas podem levar bastante tempo porque as imagens são geradas
uma por vez para respeitar a memória de vídeo.

## Limitações da primeira versão

- O SD 1.5 melhora a consistência usando a ficha visual, mas não garante rostos
  idênticos em todas as cenas. LoRA ou IP-Adapter podem ser adicionados depois.
- A primeira versão usa uma voz de narrador por idioma. Vozes diferentes por
  personagem ficam para a próxima etapa.
- O texto não é enviado ao Pexels, OpenAI, Higgsfield ou WaveSpeed.
