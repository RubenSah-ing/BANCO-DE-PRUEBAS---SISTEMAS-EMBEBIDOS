# =====================================
# NOMBRE: Ruben Sahuquillo Redondo
# ASIGNATURA: Lenguajes de Alto Nivel para Aplicaciones Industriales
# DESCRIPCION: Libreria desarrollada para facilitar la comunicacion con el banco de pruebas
# =====================================


#----- LIBRERIAS -----#
import paho.mqtt.client as mqtt
import subprocess
import time
import json
import os
import csv
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


#----- CLASE -----#
class TestBench:
    #Constructor
    def __init__(self):
        self._pct = []
        self._speeds = []
        self._thrusts = []
        self._torques = []
        self._currents = []
        self._voltages = []

        self._client = None
        self.topicReceive = None
        self.topicSend = None
        self._brokerIP = None
        self._brokerPORT = None
        self.first_message_received = False

        self._Kt = []
        self._Kv = []
        self._potencia_electrica = []
        self._potencia_mecanica = []
        self._rendimiento = []

        self._testName = ""
        self._testInfo = ""

        self._config = {}

        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.fig_path  = os.path.join(base_path, "fig")
        self.log_path  = os.path.join(base_path, "logs")

        os.makedirs(self.fig_path, exist_ok=True)
        os.makedirs(self.log_path, exist_ok=True)


    #Configurar broker MQTT
    def configMQTTBroker(self, broker_ip, broker_port, mosquitto_path = r"C:\Program Files\mosquitto\mosquitto.exe", mosquitto_conf = r"C:\Program Files\mosquitto\mosquitto.conf"):
        """Inicializa el broker MQTT si no está inicializado"""
        self._brokerIP = str(broker_ip)
        self._brokerPORT = int(broker_port)

        try:
            # Si el borker mosquito no esta en la lista de tareas en ejecucion
            if not any("mosquitto" in p for p in os.popen('tasklist').read().splitlines()):
                # Iniciar subproceso, lanzado mosquito cy su configuracion
                subprocess.Popen(f'"{mosquitto_path}" -v -c "{mosquitto_conf}"',
                                 shell=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL
                                )
                print("Broker Mosquitto iniciado en segundo plano.")
                time.sleep(2)
            # Si esta en la lista de tareas en ejecucion
            else:
                print("Broker Mosquitto en ejecución.")

        except Exception as e:
            print(f"Error al iniciar el broker: {e}")


    # Configurar MQTT
    def configMQTT(self, topicSend, topicReceive):
        """Configura la conexión MQTT y se realiza la subscripción a los tópicos indicados"""
        self.topicSend = topicSend
        self.topicReceive = topicReceive
        # Si la ip del broker no es None o el puerto del broker es None, lanzar excepcion
        if self._brokerIP is None or self._brokerPORT is None:
            raise ValueError("Debe configurar primero el broker con configMQTTBroker()")
        
        # Si ip y puerto son validos
        else:
            # Si el cliente no es None
            if self._client is None:
                try:
                    self._client = mqtt.Client()
                    self._client.on_message = self.receiveMQTT
                    self._client.connect(self._brokerIP, self._brokerPORT)
                    self._client.subscribe(topicReceive)
                    self._client.loop_start()
                    print("\nCliente MQTT conectado\n")
                    print(f"Publica en Tópico -> {topicSend}\n")
                    print(f"Recibe en Tópico -> {topicReceive}")

                except Exception as e:
                    print(f"Error al conectar MQTT: {e}")


    #Enviar MQTT
    def sendMQTT(self, topicSend, msg):
        #Si el cliente es None
        if self._client is None:
            print("Error: cliente MQTT no inicializado.")
            return
        #Si el cliente no es None, publicar mensaje MQTT
        else:
            try:
                self._client.publish(topicSend, msg)

            except Exception as e:
                print(f"No se pudo enviar MQTT: {e}")


    #Callback de recepcion del MQTT
    def receiveMQTT(self, client, userdata, msg):
        if not self.first_message_received:
            self.first_message_received = True
            return
        
        try:
            payload = msg.payload.decode().strip()

            if not payload:
                print("Mensaje MQTT vacío recibido.")
                return

            data = json.loads(payload)

            # Validar que data sea un diccionario
            if not isinstance(data, dict):
                print(f"Mensaje MQTT no válido (no es un dict JSON): {payload}")
                return
            
            print(data)

            pct = round(data.get("%", 0.0), 2)
            rpm = round(data.get("RPM", 0.0), 2)
            empuje = round(data.get("Empuje", 0.0), 2)
            par = round(data.get("Par", 0.0), 2)
            intensidad = round(data.get("Intensidad", 0.0), 2)
            voltaje = 12.00

            self._pct.append(pct)
            self._speeds.append(rpm)
            self._thrusts.append(empuje)
            self._torques.append(par)
            self._currents.append(intensidad)
            self._voltages.append(voltaje)

            vel_last = self._config.get("vel_last") if self._config else None

            if vel_last is not None and pct >= vel_last:
                self.finish()

        except json.JSONDecodeError:
            print(f"No es JSON, es info: {payload}")
        except Exception as e:
            print(f"Error al recibir datos MQTT: {e}")

    #SET INFORMACION DEL TEST
    def setTestInfo(self, propeller, pitch, diameter, motor, kv, max_current):
        self._testName = f"Test - Motor {motor} - Propeller {propeller} {diameter}x{pitch}"
        self._testInfo = f"Test - Motor {motor} (KV = {kv}, Imax = {max_current}) - Propeller {propeller} {diameter}x{pitch}"


    #FINALIZAR ENSAYO
    def finish(self, name="testbench_result"):
        """Genera automáticamente informe y figura al finalizar el test."""
        print("\nGenerando informe CSV y figuras...")

        self._Kt, self._Kv, self._rendimiento, self._potencia_electrica, self._potencia_mecanica = self.computeParameters()

        self.reportGenerate(name)

        self.figureGenerate(name)

        print(f"Informe generado en: {self.log_path}")
        print(f"Gráficas generadas en: {self.fig_path}")
        print("\nProceso finalizado.")


    #CALCULAR PARÁMETROS ENSAYO
    def computeParameters(self):
        """Cálculo de parámetros del motor con unidades SI"""

        self._Kt = []
        self._Kv = []
        self._rendimiento = []
        self._potencia_electrica = []
        self._potencia_mecanica = []

        if not self._currents or not self._voltages or not self._torques or not self._speeds:
            return [], [], [], [], []
        
        else:
            # CONVERSIONES
            torques_nm = [(((t / 1000) * 9.81) / 100) for t in self._torques]  # g·cm → N·m
            omegas = [rpm * 2 * math.pi / 60 for rpm in self._speeds]  # RPM → rad/s

            # Kt (Nm / A)
            for torque, current in zip(torques_nm, self._currents):
                if current != 0:
                    self._Kt.append(torque / current)
                else:
                    self._Kt.append(0)


            # Kv (rad/s / V)
            for omega, voltage in zip(omegas, self._voltages):
                if voltage != 0:
                    self._Kv.append(omega / voltage)
                else:
                    self._Kv.append(0)


            # Potencias
            self._potencia_electrica = [
                v * i for v, i in zip(self._voltages, self._currents)
            ]

            self._potencia_mecanica = [
                t * w for t, w in zip(torques_nm, omegas)
            ]


            # Rendimiento (imperfecto)
            for pe, pm in zip(self._potencia_electrica, self._potencia_mecanica):
                if pe != 0:
                    self._rendimiento.append(pm / pe)
                else:
                    self._rendimiento.append(0)


            return self._Kt, self._Kv, self._rendimiento, self._potencia_electrica, self._potencia_mecanica



    #Generar informe
    def reportGenerate(self, filename):
        """Genera un informe .csv con los resultados del test"""

        fullpath = os.path.join(self.log_path, self._testInfo + '.csv')

        with open(fullpath, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["%", "RPM", "Empuje", "Par", "Intensidad", "Voltaje"])

            for row in zip(self._pct, self._speeds, self._thrusts, self._torques, self._currents, self._voltages):
                writer.writerow(row)
            
            writer.writerow([])
            writer.writerow(["Kt", self._Kt])
            writer.writerow(["Kv", self._Kv])
            writer.writerow(["Potencia Eléctrica (W)"])
            writer.writerow(self._potencia_electrica)
            writer.writerow(["Potencia Mecánica (W)"])
            writer.writerow(self._potencia_mecanica)
            writer.writerow(["Rendimiento", self._rendimiento])


    #Generar figuras
    def figureGenerate(self, name):
        """Genera gráficas con las curvas obtenidas en el ensayo"""

        print("LEN pct:", len(self._pct))
        print("LEN speeds:", len(self._speeds))
        print("LEN Kt:", len(self._Kt))
        print("LEN Kv:", len(self._Kv))
        print("LEN rendimiento:", len(self._rendimiento))


        if not self._pct:
            print("No hay datos registrados para generar figuras.")
            return

        fullpath = os.path.join(self.fig_path, self._testName + ".png")

        fig, axs = plt.subplots(4, 2, figsize=(12, 18))
        fig.suptitle("Resultados del Test Bench", fontsize=16)

        axs[0, 0].plot(self._pct, self._speeds)
        axs[0, 0].set_title("RPM vs %")
        axs[0, 0].set_xlabel("%")
        axs[0, 0].set_ylabel("RPM")

        axs[0, 1].plot(self._pct, self._thrusts)
        axs[0, 1].set_title("Empuje vs %")
        axs[0, 1].set_xlabel("%")
        axs[0, 1].set_ylabel("Empuje (g)")

        axs[1, 0].plot(self._pct, self._torques)
        axs[1, 0].set_title("Par vs %")
        axs[1, 0].set_xlabel("%")
        axs[1, 0].set_ylabel("Par (g*cm)")

        axs[1, 1].plot(self._pct, self._currents)
        axs[1, 1].set_title("Intensidad vs %")
        axs[1, 1].set_xlabel("%")
        axs[1, 1].set_ylabel("Intensidad (A)")

        axs[2, 0].plot(self._pct, self._voltages)
        axs[2, 0].set_title("Voltaje vs %")
        axs[2, 0].set_xlabel("%")
        axs[2, 0].set_ylabel("Voltaje (V)")

        axs[2, 1].plot(self._pct, self._Kt)
        axs[2, 1].set_title("Kt vs %")
        axs[2, 1].set_xlabel("%")
        axs[2, 1].set_ylabel("Kt (N·m/A)")

        axs[3, 0].plot(self._pct, self._Kv)
        axs[3, 0].set_title("Kv vs %")
        axs[3, 0].set_xlabel("%")
        axs[3, 0].set_ylabel("Kv (rad/s/V)")

        axs[3, 1].plot(self._pct, self._rendimiento)
        axs[3, 1].set_title("Rendimiento vs %")
        axs[3, 1].set_xlabel("%")
        axs[3, 1].set_ylabel("Rendimiento (-)")

        plt.tight_layout()
        fig.savefig(fullpath, dpi=300)
        print("Figuras generadas")
        plt.close()

    #Set configuracion del test
    def setTestConfig(self, config):
        """Añade los paraámetros del test al atributo _config"""
        self._config = config


# ----- MAIN ----- #
# Si el programa se ejecuta desde este archivo con este nombre, instanciar objeto de TestBench()
if __name__ == '__main__':
    tb = TestBench()