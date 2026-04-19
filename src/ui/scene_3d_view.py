import os
import numpy as np
import trimesh
import xml.etree.ElementTree as ET
import pyqtgraph.opengl as gl
from scipy.spatial.transform import Rotation


COLORS = [
    (0.31, 0.76, 0.97, 0.9),
    (0.51, 0.78, 0.52, 0.9),
    (1.00, 0.72, 0.30, 0.9),
    (0.94, 0.38, 0.57, 0.9),
    (0.73, 0.41, 0.78, 0.9),
    (0.30, 0.71, 0.67, 0.9),
    (1.00, 0.95, 0.46, 0.9),
    (1.00, 0.54, 0.40, 0.9),
] # des couleurs aleatoire pour 8 objets diff 


def load_meshes_from_urdf(urdf_path):
    """Charge les meshes visuels du URDF en appliquant les origins de chaque visual."""
    tree = ET.parse(urdf_path)
    root = tree.getroot()
    urdf_dir = os.path.dirname(urdf_path)
    meshes = []

    for link in root.findall('link'):
        for visual in link.findall('visual'):
            geom = visual.find('geometry')
            if geom is None:
                continue
            mesh_tag = geom.find('mesh')
            if mesh_tag is None:
                continue
            mesh_path = os.path.join(urdf_dir, mesh_tag.get('filename'))
            if not os.path.exists(mesh_path):
                continue
            try:
                m = trimesh.load(mesh_path, force='mesh')
                origin = visual.find('origin')
                if origin is not None:
                    xyz = [float(v) for v in origin.get('xyz', '0 0 0').split()]
                    rpy = [float(v) for v in origin.get('rpy', '0 0 0').split()]
                    transform = np.eye(4)
                    transform[:3, :3] = Rotation.from_euler('xyz', rpy).as_matrix()
                    transform[:3, 3] = xyz
                    m.apply_transform(transform)
                meshes.append(m)
            except Exception:
                continue
    return meshes


class SceneView3D(gl.GLViewWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundColor('w')
        self.setCameraPosition(distance=4, elevation=30, azimuth=45)
        self._add_ground()

    def _add_ground(self):
        grid = gl.GLGridItem()
        grid.setSize(4, 4)
        grid.setSpacing(0.25, 0.25)
        grid.setColor((100, 100, 100, 80))
        self.addItem(grid)

    def update_scene(self, objetsList):
        """Charge et affiche les objets 3D a partir de la liste d'objets"""
        self.clear()
        self._add_ground()

        for i, obj in enumerate(objetsList):
            path = obj.get('path', '')
            pos = obj.get('pos', (0, 0, 0))
            color = COLORS[i % len(COLORS)]

            if path.endswith('.urdf'):
                meshes = load_meshes_from_urdf(path)
            elif path.endswith(('.obj', '.stl', '.ply')):
                m = trimesh.load(path, force='mesh')
                meshes = [m] if m is not None else []
            else:
                continue
            scale = obj.get('scale', 1.0)
            quat = obj.get('quat', None)  # (x, y, z, w)
            if quat is not None:
                rot_matrix = Rotation.from_quat(quat).as_matrix().astype(np.float32)
            else:
                rot_matrix = None
            for m in meshes:
                verts = np.array(m.vertices, dtype=np.float32) * scale
                if rot_matrix is not None:
                    verts = verts @ rot_matrix.T
                faces = np.array(m.faces, dtype=np.uint32)
                face_colors = np.tile(color, (len(faces), 1)).astype(np.float32)
                md = gl.MeshData(vertexes=verts, faces=faces, faceColors=face_colors)
                mesh_item = gl.GLMeshItem(
                    meshdata=md,
                    smooth=True,
                    drawEdges=False,
                    shader='shaded',
                )
                mesh_item.translate(pos[0], pos[1], pos[2])
                self.addItem(mesh_item)
