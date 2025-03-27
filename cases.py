import sqlite3
import math

class CaseDatabase:
    def __init__(self, db_name='casos.db'):
        self.db_name = db_name
        self.CreateTable()

    def _connect(self):
        """
        Establish a connection to the database
        
        Returns:
            sqlite3.Connection: Connection object
        """
        return sqlite3.connect(self.db_name)

    def CreateTable(self):
        """
        Create the table in the database if it does not exist.
        
        Returns:
            None
        """
        conn = self._connect()
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS casos (
                id INTEGER PRIMARY KEY,
                distancia_obstaculo REAL,
                angulo_obstaculo REAL,
                cenarios TEXT,
                v REAL,
                w REAL
            )
        ''')
        conn.commit()
        conn.close()

    def AddCase(self, distancia_obstaculo, angulo_obstaculo, cenario, v, w):
        """
        Add a case to the database.
        
        Args:
            distancia_obstaculo (float): Distance to the obstacle
            angulo_obstaculo (float): Angle to the obstacle
            cenario (str): Scenario
            v (float): Linear velocity
            w (float): Angular velocity

        Returns:
            None
        """
        try:
            conn = self._connect()
            c = conn.cursor()
            c.execute('''
                INSERT INTO casos (distancia_obstaculo, angulo_obstaculo, cenarios, v, w)
                VALUES (?, ?, ?, ?, ?)
            ''', (distancia_obstaculo, angulo_obstaculo, cenario, v, w))
            case_id = c.lastrowid 
            conn.commit()
            conn.close()

        except Exception as e:
            print(f"Erro ao adicionar caso: {e}")

    def SearchSimilarCase(self, distancia_obstaculo, angulo_obstaculo, cenario, tolerance_distance=0.5, tolerance_angle=0.17):
        """
        Search for similar cases in the database.
        
        Args:
            distancia_obstaculo (float): Distance to the obstacle
            angulo_obstaculo (float): Angle to the obstacle
            cenario (str): Scenario
            tolerance_distance (float): Tolerance for distance
            tolerance_angle (float): Tolerance for angle
        
        Returns:
            list: List of similar cases"""
        conn = self._connect()
        c = conn.cursor()

        angulo_min = angulo_obstaculo - tolerance_angle
        angulo_max = angulo_obstaculo + tolerance_angle

        # Ajuste cíclico para garantir que a busca considere os limites corretamente
        if angulo_min > angulo_max:
            angulo_min, angulo_max = angulo_max, angulo_min

        c.execute('''
            SELECT * FROM casos 
            WHERE cenarios = ? AND 
                  distancia_obstaculo BETWEEN ? AND ? AND 
                  angulo_obstaculo BETWEEN ? AND ?
        ''', (cenario, distancia_obstaculo - tolerance_distance, distancia_obstaculo + tolerance_distance, angulo_min, angulo_max))

        casos = c.fetchall()
        conn.close()

        if not casos:
            return None # Return None if no similar cases are found
        
        casos_ordenados = sorted(casos, key=lambda case: 
            abs(case[1] - distancia_obstaculo) / tolerance_distance + 
            abs(case[2] - angulo_obstaculo) / tolerance_angle
        )
        return casos_ordenados[0] 
            
    def AllCases(self):
        """
        Retrieve all cases from the database.
        
        Returns:
            list: List of all cases
        """
        conn = self._connect()
        c = conn.cursor()

        c.execute('SELECT * FROM casos')

        casos = c.fetchall()
        conn.close()
        return casos

if __name__ == "__main__":

    db = CaseDatabase()

    # Exibir todos os casos no banco de dados
    todos_casos = db.AllCases()
    print("Todos os casos:")
    for caso in todos_casos:
        print(caso)
