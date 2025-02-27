import sqlite3

class CaseDatabase:
    def __init__(self, db_name='casos.db'):
        self.db_name = db_name

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
                distancia_apos REAL,
                angulo_apos REAL
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
            distancia_apos (float): Distance after the obstacle
            angulo_apos (float): Angle after the obstacle

        Returns:
            None
        """
        conn = self._connect()
        c = conn.cursor()
        c.execute('''
            INSERT INTO casos (distancia_obstaculo, angulo_obstaculo, cenarios, distancia_apos, angulo_apos)
            VALUES (?, ?, ?, ?, ?)
        ''', (distancia_obstaculo, angulo_obstaculo, cenario, v, w))
        conn.commit()
        conn.close()

    def SearchSimilarCase(self, distancia_obstaculo, angulo_obstaculo, cenario, tolerance_distance=1, tolerance_angle=5):
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

        c.execute('''
            SELECT * FROM casos 
            WHERE cenarios = ? AND 
                  distancia_obstaculo BETWEEN ? AND ? AND 
                  angulo_obstaculo BETWEEN ? AND ?
        ''', (cenario, distancia_obstaculo - tolerance_distance, distancia_obstaculo + tolerance_distance, angulo_obstaculo - tolerance_angle, angulo_obstaculo + tolerance_angle))

        casos = c.fetchall()
        conn.close()
        return casos

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
    db.CreateTable()

    # Exemplo de adicionar um caso
    db.AddCase(5.0, 45.0, "caminho livre", 4.5, 50.0)

    # Exemplo de busca por casos semelhantes
    casos_similares = db.SearchSimilarCase(5.0, 45.0, "caminho livre")
    print("Casos semelhantes:", casos_similares)

    # Exibir todos os casos no banco de dados
    todos_casos = db.AllCases()
    print("Todos os casos:")
    for caso in todos_casos:
        print(caso)
