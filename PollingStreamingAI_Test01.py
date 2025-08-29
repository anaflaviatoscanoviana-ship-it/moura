#!/usr/bin/python
# -*- coding:utf-8 -*-

import datetime
import sys, os
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),
                                             os.path.pardir)))
from CommonUtils import kbhit

from Automation.BDaq import *
from Automation.BDaq.WaveformAiCtrl import WaveformAiCtrl
from Automation.BDaq.BDaqApi import AdxEnumToString, BioFailed

# Configure os parâmetros a seguir
deviceDescription = "USB-4716,BID#1"
profilePath = u"C:/Advantech/DAQNavi/Examples/profile/USB-4716.xml"

startChannel = 0
channelCount = 2

sectionLength = 100
sectionCount = 0 # 0 = Modo Streaming (contínuo)

userParam = DaqEventParam()

@DaqEventCallback(None, c_void_p, POINTER(BfdAiEventArgs), c_void_p)
def OnBurnoutEvent(sender, args, userParam):
    status  = cast(args, POINTER(BfdAiEventArgs))[0]
    channel = status.Offset
    print("AI Channel%d is burntout!" % (channel))

USER_BUFFER_SIZE = channelCount * sectionLength

def AdvPollingStreamingAI():
    ret = ErrorCode.Success

    # Passo 1: Criar o controlador WaveformAiCtrl
    wfAiCtrl = WaveformAiCtrl(deviceDescription)
    wfAiCtrl.addBurnOutHandler(OnBurnoutEvent, userParam)

    dados_coletados = []

    for _ in range(1):
        # Carrega o perfil para inicializar o dispositivo
        wfAiCtrl.loadProfile = profilePath
        
        # Passo 2: Configurar os parâmetros da operação
        wfAiCtrl.conversion.channelStart = startChannel
        wfAiCtrl.conversion.channelCount = channelCount
        wfAiCtrl.conversion.clockRate    = 2000 # Taxa de amostragem TOTAL

        wfAiCtrl.record.sectionCount = sectionCount  
        wfAiCtrl.record.sectionLength = sectionLength

        # As configurações individuais de canal estão comentadas para usar os padrões do dispositivo
        # for i in range(channelCount):
            #wfAiCtrl.channels[startChannel + i].signalType      = AiSignalType.SingleEnded
            #wfAiCtrl.channels[startChannel + i].valueRange      = ValueRange.V_0To5

        # Passo 3: Preparar e iniciar a operação
        ret = wfAiCtrl.prepare()
        if BioFailed(ret):
            break

        ret = wfAiCtrl.start()
        if BioFailed(ret):
            break

        # Passo 4: Coletar dados em tempo real
        print("Coleta de dados em progresso... Pressione qualquer tecla para parar e salvar.")

        # --- LÓGICA DE TIMESTAMP MELHORADA ---
        # 1. Marca o tempo de início exato da aquisição
        hora_inicio_coleta = datetime.datetime.now()
        
        # 2. Calcula a taxa de amostragem para cada canal individualmente
        #    Se a taxa total é 2000 Hz para 2 canais, então cada canal tem 1000 amostras/segundo.
        taxa_por_canal = wfAiCtrl.conversion.clockRate / channelCount
        intervalo_por_amostra = datetime.timedelta(seconds=1.0 / taxa_por_canal)
        
        # 3. Mantém um contador de quantas amostras (por canal) já foram processadas
        contador_amostras_processadas = 0
        # --- FIM DA MELHORIA ---

        while not kbhit():
            #time.sleep( 1 / 10)
            result = wfAiCtrl.getData(USER_BUFFER_SIZE, -1)
            ret, returnedCount, data, = result[0], result[1], result[2]
            if BioFailed(ret):
                break
            print("the first sample for each channel are:")
            for i in range(channelCount):
                print("channel %d: %10.6f" % (i + startChannel, data[i]))
            # Processa o bloco de dados para adicionar o timestamp a cada leitura
            '''if returnedCount > 0:
                for i in range(0, returnedCount, channelCount):
                    amostras_da_leitura = data[i : i + channelCount]
                    if len(amostras_da_leitura) == channelCount:
                        # --- CÁLCULO PRECISO DO TIMESTAMP ---
                        # Pega o índice da amostra dentro do bloco atual (0, 1, 2, ...)
                        indice_no_bloco = i // channelCount
                        
                        # Calcula o deslocamento de tempo desde o início da coleta
                        deslocamento_total = (contador_amostras_processadas + indice_no_bloco) * intervalo_por_amostra
                        timestamp_exato = hora_inicio_coleta + deslocamento_total
                        # --- FIM DO CÁLCULO ---
                        
                        dados_coletados.append((timestamp_exato, amostras_da_leitura))
                '''
                # Atualiza o contador com o número de amostras (por canal) que acabamos de processar
            contador_amostras_processadas += (returnedCount // channelCount)

        # Passo 6: Parar a operação
        ret = wfAiCtrl.stop()

    # --- Bloco de Salvamento ---
    if dados_coletados:
        print(f"\nColeta finalizada. Salvando dados em arquivo...")

        agora = datetime.datetime.now()
        nome_do_arquivo = agora.strftime("dados_%Y-%m-%d_%H-%M-%S.txt")

        with open(nome_do_arquivo, "w") as f:
            # Escreve o cabeçalho das colunas
            cabecalho = "Timestamp, " + ", ".join([f"Canal_{i}" for i in range(startChannel, startChannel + channelCount)])
            f.write(cabecalho + "\n")

            # Percorre a lista de dados coletados e escreve no arquivo
            for amostra_completa in dados_coletados:
                timestamp, valores = amostra_completa

                # Verifica se os valores de ambos os canais atendem à condição
                if valores[0] > 0.001 and valores[1] > 0.001:
                #if True: # Descomente esta linha para salvar todos os dados, ignorando a condição
                
                    # O bloco abaixo só executa se a condição 'if' for verdadeira.
                    
                    # Formata o timestamp para incluir milissegundos
                    timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    # Formata os valores numéricos
                    valores_str = ", ".join([f"{valor:.6f}" for valor in valores])
                    # Cria a linha de texto completa
                    linha = f"{timestamp_str}, {valores_str}"
                    # Escreve a linha no arquivo
                    f.write(linha + "\n")
                    
            print(f"Arquivo '{nome_do_arquivo}' salvo com sucesso!")

    # Passo 7: Liberar recursos
    wfAiCtrl.release()
    wfAiCtrl.dispose()

    if BioFailed(ret):
        enumStr = AdxEnumToString("ErrorCode", ret.value, 256)
        print("Some error occurred. And the last error code is %#x. [%s]" %
              (ret.value, enumStr))
        
    return 0

if __name__ == '__main__':
    AdvPollingStreamingAI()