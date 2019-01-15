from builtins import range
from mupif import *
import mupif
import Pyro4
import meshgen
import math
import numpy as np
import time as timeTime
import os
import logging

log = logging.getLogger('demo01_models')

import mupif.Physics.PhysicalQuantities as PQ

timeUnits = PQ.PhysicalUnit('s', 1., [0, 0, 1, 0, 0, 0, 0, 0, 0])


def getline(f):
    while True:
        line = f.readline()
        if line == '':
            raise APIError.APIError('Error: EOF reached in input file')
        elif line[0] != '#':
            return line


@Pyro4.expose
class thermal(Application.Application):
    """ Simple stationary heat transport solver on rectangular domains"""

    def __init__(self, file="", workdir="."):
        super(thermal, self).__init__(file, workdir)
        self.morphologyType = None
        self.conductivity = Property.ConstantProperty(1, PropertyID.PID_effective_conductivity, ValueType.ValueType.Scalar,
                                                      'W/m/K')
        self.tria = False

        self.metadata.update({'name': 'thermal_nonstat', 'type': '',
                              'inputs': [
                                  {'name': 'top edge temperature Cauchy', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 3},
                                  # {'name': 'top edge temperature Cauchy coef', 'type': 'Property', 'optional': True,
                                  #  'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 23},
                                  {'name': 'top edge temperature Dirichlet', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 13},
                                  {'name': 'bottom edge temperature Cauchy', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 1},
                                  # {'name': 'bottom edge temperature Cauchy coef', 'type': 'Property', 'optional': True,
                                  #  'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 21},
                                  {'name': 'bottom edge temperature Dirichlet', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 11},
                                  {'name': 'left edge temperature Cauchy', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 4},
                                  # {'name': 'left edge temperature Cauchy coef', 'type': 'Property', 'optional': True,
                                  #  'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 24},
                                  {'name': 'left edge temperature Dirichlet', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 14},
                                  {'name': 'right edge temperature Cauchy', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 2},
                                  # {'name': 'right edge temperature Cauchy coef', 'type': 'Property', 'optional': True,
                                  #  'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 22},
                                  {'name': 'right edge temperature Dirichlet', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 12}
                              ],
                              'outputs': [
                                  {'name': 'temperature', 'obj_type': 'mupif.FieldID.FID_Temperature', 'type': 'Field',
                                   'optional': True}
                              ]})

        if self.file != "":
            self.readInput()

    def readInput(self, tria=False):
        self.tria = tria
        self.dirichletModelEdges = []
        self.convectionModelEdges = []
        try:
            lines = []
            for line in open(self.workDir + os.path.sep + self.file, 'r'):
                if not line.startswith('#'):
                    lines.append(line)
        except Exception as e:
            log.info('Current working directory is %s, file is %s' % (self.workDir, self.file))
            log.exception(e)
            exit(1)

        line = lines.pop(0)
        size = line.split()
        self.xl = float(size[0])
        self.yl = float(size[1])
        log.info("Thermal problem's dimensions: (%g, %g)" % (self.xl, self.yl))
        line = lines.pop(0)
        ne = line.split()
        self.nx = int(ne[0])
        self.ny = int(ne[1])

        for iedge in range(4):
            line = lines.pop(0)
            # print (line)
            rec = line.split()
            edge = int(rec[0])
            code = rec[1]
            temperature = float(rec[2])
            if code == 'D':
                self.dirichletModelEdges.append((edge, temperature))
            elif code == 'C':
                h = float(rec[3])
                self.convectionModelEdges.append((edge, temperature, h))

        # print (self.convectionModelEdges)

        line = lines.pop(0)
        rec = line.split()
        if len(rec) > 0:
            if rec[0] == 'Inclusion':
                self.morphologyType = 'Inclusion'
                self.scaleInclusion = float(rec[1])

    def prepareTask(self):
        self.mesh = Mesh.UnstructuredMesh()
        # generate a simple mesh here, either triangles or rectangles
        # self.xl = 0.5 # domain (0..xl)(0..yl)
        # self.yl = 0.3
        # self.nx = 10 # number of elements in x direction
        # self.ny = 10 # number of elements in y direction
        self.dx = self.xl / self.nx
        self.dy = self.yl / self.ny
        self.mesh = meshgen.meshgen((0., 0.), (self.xl, self.yl), self.nx, self.ny, self.tria)

        #
        # Model edges
        #     ----------3----------
        #     |                   |
        #     4                   2
        #     |                   |
        #     ----------1---------
        #

        # self.dirichletModelEdges=(3,4,1)#
        self.dirichletBCs = {}  # key is node number, value is prescribed temperature
        for (ide, value) in self.dirichletModelEdges:
            # print ("Dirichlet", ide)
            if ide == 1:
                for i in range(self.nx + 1):
                    self.dirichletBCs[i * (self.ny + 1)] = value
            elif ide == 2:
                for i in range(self.ny + 1):
                    self.dirichletBCs[(self.ny + 1) * (self.nx) + i] = value
            elif ide == 3:
                for i in range(self.nx + 1):
                    self.dirichletBCs[self.ny + (self.ny + 1) * (i)] = value
            elif ide == 4:
                for i in range(self.ny + 1):
                    self.dirichletBCs[i] = value

        # self.convectionModelEdges=(2,)
        self.convectionBC = []
        for (ice, value, h) in self.convectionModelEdges:
            # print ("Convection", ice)
            if ice == 1:
                for i in range(self.nx):
                    if self.tria:
                        self.convectionBC.append((2 * self.ny * i, 0, h, value))
                    else:
                        self.convectionBC.append((self.ny * i, 0, h, value))
            elif ice == 2:
                for i in range(self.ny):
                    if self.tria:
                        self.convectionBC.append(((self.nx - 1) * 2 * self.ny + 2 * i, 1, h, value))
                    else:
                        self.convectionBC.append(((self.nx - 1) * self.ny + i, 1, h, value))
            elif ice == 3:
                for i in range(self.nx):
                    if self.tria:
                        self.convectionBC.append((2 * self.ny * (i + 1) - 1, 1, h, value))
                    else:
                        self.convectionBC.append((self.ny * (i + 1) - 1, 2, h, value))
            elif ice == 4:
                for i in range(self.ny):
                    if self.tria:
                        self.convectionBC.append((2 * i + 1, 2, h, value))
                    else:
                        self.convectionBC.append((i, 3, h, value))

        self.loc = np.zeros(self.mesh.getNumberOfVertices(), dtype=np.int32)
        self.neq = 0  # number of unknowns
        self.pneq = 0  # number of prescribed equations (Dirichlet b.c.)
        # print (self.mesh.getNumberOfVertices())
        for i in range(self.mesh.getNumberOfVertices()):
            # print(i)
            if i in self.dirichletBCs:
                self.pneq += 1
            else:
                self.neq += 1
        # print ("Neq", self.neq, "Pneq", self.pneq)
        # print(self.loc)
        ineq = 0  # unknowns numbering starts from 0..neq-1
        ipneq = self.neq  # prescribed unknowns numbering starts neq..neq+pneq-1

        for i in range(self.mesh.getNumberOfVertices()):
            if i in self.dirichletBCs:
                self.loc[i] = ipneq
                ipneq += 1
            else:
                self.loc[i] = ineq
                ineq += 1
        # print (self.loc)

    def getField(self, fieldID, time, objectID=0):
        if fieldID == FieldID.FID_Temperature:
            values = []
            for i in range(self.mesh.getNumberOfVertices()):
                if time.getValue() == 0.0:  # put zeros everywhere
                    values.append((0.,))
                else:
                    values.append((self.T[self.loc[i]],))
            return Field.Field(self.mesh, FieldID.FID_Temperature, ValueType.ValueType.Scalar, 'C', time, values)
        elif fieldID == FieldID.FID_Material_number:
            values = []
            for e in self.mesh.cells():
                if self.isInclusion(e) and self.morphologyType == 'Inclusion':
                    values.append((1,))
                else:
                    values.append((0,))
            # print (values)
            return Field.Field(self.mesh, FieldID.FID_Material_number, ValueType.ValueType.Scalar, PQ.getDimensionlessUnit(),
                               time, values, fieldType=Field.FieldType.FT_cellBased)
        else:
            raise APIError.APIError('Unknown field ID')

    def isInclusion(self, e):
        vertices = e.getVertices()
        c1 = vertices[0].coords
        c2 = vertices[1].coords
        c3 = vertices[2].coords
        c4 = vertices[3].coords
        xCell = (c1[0] + c2[0] + c3[0] + c4[0]) / 4.  # vertex center
        yCell = (c1[1] + c2[1] + c3[1] + c4[1]) / 4.  # vertex center
        radius = min(self.xl, self.yl) * self.scaleInclusion
        xCenter = self.xl / 2.  # domain center
        yCenter = self.yl / 2.  # domain center
        if (math.sqrt((xCell - xCenter) * (xCell - xCenter) + (yCell - yCenter) * (yCell - yCenter)) < radius):
            return True
            # print (xCell,yCell)
        return False

    def solveStep(self, tstep, stageID=0, runInBackground=False):
        self.prepareTask()
        mesh = self.mesh
        self.volume = 0.0
        self.integral = 0.0

        numNodes = mesh.getNumberOfVertices()
        numElements = mesh.getNumberOfCells()
        ndofs = 4

        # print numNodes
        # print numElements
        # print ndofs

        start = timeTime.time()
        log.info(self.getApplicationSignature())
        log.info("Number of equations: %d" % self.neq)

        # connectivity
        c = np.zeros((numElements, 4), dtype=np.int32)
        for e in range(0, numElements):
            for i in range(0, 4):
                c[e, i] = self.mesh.getVertex(mesh.getCell(e).vertices[i]).label
        # print "connectivity :",c

        # Global matrix and global vector
        kuu = np.zeros((self.neq, self.neq))
        kpp = np.zeros((self.pneq, self.pneq))
        kup = np.zeros((self.neq, self.pneq))
        # A = np.zeros((self.neq, self.neq ))
        b = np.zeros(self.neq)
        # solution vector
        self.T = np.zeros(self.neq + self.pneq)  # vector of temperatures

        # initialize prescribed Temperatures in current solution vector (T):
        for i in range(self.mesh.getNumberOfVertices()):
            if i in self.dirichletBCs:
                ii = self.loc[i]
                self.T[ii] = self.dirichletBCs[i]  # assign temperature

        log.info("Assembling ...")
        for e in mesh.cells():
            A_e = self.compute_elem_conductivity(e, self.conductivity.getValue(tstep.getTime()))

            # #Assemble
            # print e, self.loc[c[e.number-1,0]],self.loc[c[e.number-1,1]], self.loc[c[e.number-1,2]], self.loc[c[e.number-1,3]]
            for i in range(ndofs):  # loop of dofs
                ii = self.loc[c[e.number - 1, i]]  # code number
                if ii < self.neq:  # unknown to be solved
                    for j in range(ndofs):
                        jj = self.loc[c[e.number - 1, j]]
                        if jj < self.neq:
                            kuu[ii, jj] += A_e[i, j]
                        else:
                            kup[ii, jj - self.neq] += A_e[i, j]
                else:  # prescribed value
                    for j in range(ndofs):
                        jj = self.loc[c[e.number - 1, j]]
                        if jj >= self.neq:
                            kpp[ii - self.neq, jj - self.neq] += A_e[i, j]

        # print (A)
        # print (b)

        # add boundary terms
        # print ('Convection BC', self.convectionBC)
        for i in self.convectionBC:
            # print "Processing bc:", i
            elem = mesh.getCell(i[0])
            side = i[1]
            h = i[2]
            Te = i[3]
            # print ("h:%f Te:%f" % (h, Te))

            n1 = elem.getVertices()[side]
            # print n1
            if (side == 3):
                n2 = elem.getVertices()[0]
            else:
                n2 = elem.getVertices()[side + 1]

            length = math.sqrt((n2.coords[0] - n1.coords[0]) * (n2.coords[0] - n1.coords[0]) +
                               (n2.coords[1] - n1.coords[1]) * (n2.coords[1] - n1.coords[1]))

            # print h, Te, length

            # boundary_lhs=h*(np.dot(N.T,N))
            boundary_lhs = np.zeros((2, 2))
            if self.tria:
                boundary_lhs[0, 0] = h * (1. / 4.) * length
                boundary_lhs[0, 1] = h * (1. / 4.) * length
                boundary_lhs[1, 0] = h * (1. / 4.) * length
                boundary_lhs[1, 1] = h * (1. / 4.) * length
            else:
                boundary_lhs[0, 0] = h * (1. / 3.) * length
                boundary_lhs[0, 1] = h * (1. / 6.) * length
                boundary_lhs[1, 0] = h * (1. / 6.) * length
                boundary_lhs[1, 1] = h * (1. / 3.) * length

            # boundary_rhs=h*Te*N.T
            boundary_rhs = np.zeros((2, 1))
            boundary_rhs[0] = h * (1. / 2.) * length * Te
            boundary_rhs[1] = h * (1. / 2.) * length * Te

            # #Assemble
            loci = [n1.number, n2.number]
            # print loci
            for i in range(2):  # loop nb of dofs
                ii = self.loc[loci[i]]
                if ii < self.neq:
                    for j in range(2):
                        jj = self.loc[loci[j]]
                        if jj < self.neq:
                            # print "Assembling bc ", ii, jj, boundary_lhs[i,j]
                            kuu[ii, jj] += boundary_lhs[i, j]
                    b[ii] += boundary_rhs[i]

        self.r = np.zeros(self.pneq)  # reactions

        # solve linear system
        log.info("Solving thermal problem")
        # self.rhs = np.zeros(self.neq)
        self.rhs = b - np.dot(kup, self.T[self.neq:self.neq + self.pneq])
        self.T[:self.neq] = np.linalg.solve(kuu, self.rhs)
        self.r = np.dot(kup.transpose(), self.T[:self.neq]) + np.dot(kpp, self.T[self.neq:self.neq + self.pneq])
        # print (self.r)

        log.info("Done")
        log.info("Time consumed %f s" % (timeTime.time() - start))

    def compute_B(self, elem, lc):
        # computes gradients of shape functions of given element
        vertices = elem.getVertices()

        if isinstance(elem, Cell.Quad_2d_lin):
            c1 = vertices[0].coords
            c2 = vertices[1].coords
            c3 = vertices[2].coords
            c4 = vertices[3].coords

            B11 = 0.25 * (c1[0] - c2[0] - c3[0] + c4[0])
            B12 = 0.25 * (c1[0] + c2[0] - c3[0] - c4[0])
            B21 = 0.25 * (c1[1] - c2[1] - c3[1] + c4[1])
            B22 = 0.25 * (c1[1] + c2[1] - c3[1] - c4[1])

            C11 = 0.25 * (c1[0] - c2[0] + c3[0] - c4[0])
            C12 = 0.25 * (c1[0] - c2[0] + c3[0] - c4[0])
            C21 = 0.25 * (c1[1] - c2[1] + c3[1] - c4[1])
            C22 = 0.25 * (c1[1] - c2[1] + c3[1] - c4[1])

            # local coords
            ksi = lc[0]
            eta = lc[1]

            B = np.zeros((2, 2))
            B[0, 0] = (1. / elem.getTransformationJacobian(lc)) * (B22 + ksi * C22)
            B[0, 1] = (1. / elem.getTransformationJacobian(lc)) * (-B21 - eta * C21)
            B[1, 0] = (1. / elem.getTransformationJacobian(lc)) * (-B12 - ksi * C12)
            B[1, 1] = (1. / elem.getTransformationJacobian(lc)) * (B11 + eta * C11)

            dNdksi = np.zeros((2, 4))
            dNdksi[0, 0] = 0.25 * (1. + eta)
            dNdksi[0, 1] = -0.25 * (1. + eta)
            dNdksi[0, 2] = -0.25 * (1. - eta)
            dNdksi[0, 3] = 0.25 * (1. - eta)
            dNdksi[1, 0] = 0.25 * (1. + ksi)
            dNdksi[1, 1] = 0.25 * (1. - ksi)
            dNdksi[1, 2] = -0.25 * (1. - ksi)
            dNdksi[1, 3] = -0.25 * (1. + ksi)

            Grad = np.zeros((2, 4))
        elif isinstance(elem, Cell.Triangle_2d_lin):
            c1 = vertices[0].coords
            c2 = vertices[1].coords
            c3 = vertices[2].coords
            # local coords
            ksi = lc[0]
            eta = lc[1]
            B = np.zeros((2, 2))
            B[0, 0] = (1. / elem.getTransformationJacobian(lc)) * (c2[1] - c3[1])
            B[0, 1] = (1. / elem.getTransformationJacobian(lc)) * (-c1[1] + c3[1])
            B[1, 0] = (1. / elem.getTransformationJacobian(lc)) * (-c2[0] + c3[0])
            B[1, 1] = (1. / elem.getTransformationJacobian(lc)) * (c1[0] - c3[0])
            dNdksi = np.zeros((2, 3))
            dNdksi[0, 0] = 1  # N1=ksi, N2=eta, N3=1-ksi-eta
            dNdksi[0, 1] = 0
            dNdksi[0, 2] = -1
            dNdksi[1, 0] = 0
            dNdksi[1, 1] = 1
            dNdksi[1, 2] = -1
            Grad = np.zeros((2, 4))

        Grad = np.dot(B, dNdksi)
        # print Grad
        return Grad

    def compute_elem_conductivity(self, e, k):
        # compute element conductivity matrix
        numVert = e.getNumberOfVertices()
        A_e = np.zeros((numVert, numVert))
        b_e = np.zeros((numVert, 1))
        rule = IntegrationRule.GaussIntegrationRule()

        ngp = rule.getRequiredNumberOfPoints(e.getGeometryType(), 2)
        pnts = rule.getIntegrationPoints(e.getGeometryType(), ngp)

        # print "e : ",e.number-1
        # print "ngp :",ngp
        # print "pnts :",pnts

        for p in pnts:  # loop over ips
            detJ = e.getTransformationJacobian(p[0])
            # print "Jacobian: ",detJ

            dv = detJ * p[1]
            # print "dv :",dv

            N = np.zeros((1, numVert))
            tmp = e._evalN(p[0])
            N = np.asarray(tmp)
            # print "N :",N

            x = e.loc2glob(p[0])
            # print "global coords :", x

            # conductivity
            # k=self.conductivity.getValue()
            if self.morphologyType == 'Inclusion':
                if self.isInclusion(e):
                    k = 0.001

            Grad = np.zeros((2, numVert))
            Grad = self.compute_B(e, p[0])
            # print "Grad :",Grad
            K = np.zeros((numVert, numVert))
            K = k * dv * (np.dot(Grad.T, Grad))

            # Conductivity matrix
            for i in range(numVert):  # loop dofs
                for j in range(numVert):
                    A_e[i, j] += K[i, j]
        return A_e

    def getProperty(self, propID, time, objectID=0):
        if propID == PropertyID.PID_effective_conductivity:
            # average reactions from solution - use nodes on edge 4 (coordinate x==0.)
            sumQ = 0.
            for i in range(self.mesh.getNumberOfVertices()):
                coord = (self.mesh.getVertex(i).getCoordinates())
                if coord[0] < 1.e-6:
                    ipneq = self.loc[i]
                    if ipneq >= self.neq:
                        sumQ -= self.r[ipneq - self.neq]
            eff_conductivity = sumQ / self.yl * self.xl / (
                        self.dirichletBCs[(self.ny + 1) * (self.nx + 1) - 1] - self.dirichletBCs[0])
            return Property.ConstantProperty(eff_conductivity, PropertyID.PID_effective_conductivity,
                                             ValueType.ValueType.Scalar, 'W/m/K', time, 0)
        else:
            raise APIError.APIError('Unknown property ID')

    def setProperty(self, property, objectID=0):
        if property.getPropertyID() == PropertyID.PID_effective_conductivity:
            # remember the mapped value
            self.conductivity = property.inUnitsOf('W/m/K')
            # log.info("Assigning effective conductivity %f" % self.conductivity.getValue() )
        elif property.getPropertyID() == PropertyID.PID_Temperature:
            # convection
            for edge_id in range(1, 5):
                if objectID == edge_id:
                    edge_found = False
                    for edge in self.convectionModelEdges:
                        if edge[0] == edge_id:
                            idx = self.convectionModelEdges.index(edge)
                            self.convectionModelEdges[idx] = (edge_id, property.getValue()[0], edge[2])
                            edge_found = True
                    if not edge_found:
                        self.convectionModelEdges.append((edge_id, property.getValue()[0], 1.))
            # Dirichlet
            for edge_id in range(1, 5):
                if objectID == edge_id+10:
                    edge_found = False
                    for edge in self.dirichletModelEdges:
                        if edge[0] == edge_id:
                            idx = self.dirichletModelEdges.index(edge)
                            self.dirichletModelEdges[idx] = (edge_id, property.getValue()[0])
                            edge_found = True
                    if not edge_found:
                        self.dirichletModelEdges.append((edge_id, property.getValue()[0]))

        else:
            raise APIError.APIError('Unknown property ID')

    def getCriticalTimeStep(self):
        return PQ.PhysicalQuantity(100.0, 's')

    def getAssemblyTime(self, tstep):
        return tstep.getTime()

    def getApplicationSignature(self):
        return "Stationary thermal-demo-solver, ver 1.0"


@Pyro4.expose
class thermal_nonstat(thermal):
    """ Simple non-stationary (transient) heat transport solver on rectangular domains"""

    def __init__(self, file="", workdir="."):
        super(thermal_nonstat, self).__init__(file, workdir)
        self.capacity = 1.0  # J/kg/K
        self.density = 1.0
        self.Tau = 0.5
        self.init = True

        self.metadata.update({'name': 'thermal_nonstat', 'type': '',
                              'inputs': [
                                  {'name': 'top edge temperature convection', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 3},
                                  # {'name': 'top edge temperature HT coef', 'type': 'Property', 'optional': True,
                                  #  'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 23},
                                  {'name': 'top edge temperature Dirichlet', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 13},
                                  {'name': 'bottom edge temperature convection', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 1},
                                  # {'name': 'bottom edge temperature HT coef', 'type': 'Property', 'optional': True,
                                  #  'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 21},
                                  {'name': 'bottom edge temperature Dirichlet', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 11},
                                  {'name': 'left edge temperature convection', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 4},
                                  # {'name': 'left edge temperature HT coef', 'type': 'Property', 'optional': True,
                                  #  'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 24},
                                  {'name': 'left edge temperature Dirichlet', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 14},
                                  {'name': 'right edge temperature convection', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 2},
                                  # {'name': 'right edge temperature HT coef', 'type': 'Property', 'optional': True,
                                  #  'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 22},
                                  {'name': 'right edge temperature Dirichlet', 'type': 'Property', 'optional': True,
                                   'obj_type': 'mupif.FieldID.FID_Temperature', 'obj_id': 12}
                              ],
                              'outputs': [
                                  {'name': 'temperature', 'obj_type': 'mupif.FieldID.FID_Temperature', 'type': 'Field',
                                   'optional': True}
                              ]})

        if self.file != "":
            self.readInput(tria=True)

    def getApplicationSignature(self):
        return "Nonstat-Thermal-demo-solver, ver 1.0"

    def finishStep(self, tstep):
        return

    def getCriticalTimeStep(self):
        return PQ.PhysicalQuantity(100.0, 's')

    def getAssemblyTime(self, tstep):
        return tstep.getTime() - tstep.getTimeIncrement() * self.Tau

    def compute_elem_capacity(self, e):
        # compute element capacity matrix
        numVert = e.getNumberOfVertices()
        A_e = np.zeros((numVert, numVert))
        rule = IntegrationRule.GaussIntegrationRule()

        ngp = rule.getRequiredNumberOfPoints(e.getGeometryType(), 2)
        pnts = rule.getIntegrationPoints(e.getGeometryType(), ngp)

        # print "e : ",e.number-1
        # print "ngp :",ngp
        # print "pnts :",pnts

        for p in pnts:  # loop over ips
            detJ = e.getTransformationJacobian(p[0])
            # print "Jacobian: ",detJ

            dv = detJ * p[1]
            # print "dv :",dv

            N = np.zeros((1, numVert))
            tmp = e._evalN(p[0])
            N = np.asarray(tmp)
            # print "N :",N

            c = self.capacity * self.density
            if self.morphologyType == 'Inclusion':
                if self.isInclusion(e):
                    c = 0.001

            C = np.zeros((numVert, numVert))
            C = c * dv * (np.dot(N.T, N))

            # Conductivity matrix
            A_e = np.add(A_e, C)
        return A_e

    def solveStep(self, tstep, stageID=0, runInBackground=False):
        self.prepareTask()
        mesh = self.mesh
        self.volume = 0.0
        self.integral = 0.0
        dt = tstep.getTimeIncrement().inUnitsOf(timeUnits).getValue()

        if tstep.getNumber() == 0:  # assign mesh only for 0th time step
            return

        numNodes = mesh.getNumberOfVertices()
        numElements = mesh.getNumberOfCells()

        ndofs = 3 if self.tria else 4

        # print numNodes
        # print numElements
        # print ndofs

        start = timeTime.time()
        log.info(self.getApplicationSignature())
        log.info("Number of equations: %d" % self.neq)
        # connectivity
        c = np.zeros((numElements, ndofs), dtype=np.int32)
        c.fill(-1)
        for e in range(0, numElements):
            numVert = self.mesh.getCell(e).getNumberOfVertices()
            for i in range(0, numVert):
                c[e, i] = self.mesh.getVertex(mesh.getCell(e).vertices[i]).label
        # print ('connectivity :',c)

        if (self.init):  # do only once
            # Global matrix and global vector -> assuming constant time step size
            self.kuu = np.zeros((self.neq, self.neq))
            self.kpp = np.zeros((self.pneq, self.pneq))
            self.kup = np.zeros((self.neq, self.pneq))
            self.P = np.zeros((self.neq + self.pneq, self.neq + self.pneq))
            self.init = False

            log.info("Assembling ...")
            for e in mesh.cells():
                K_e = self.compute_elem_conductivity(e, self.conductivity.getValue(tstep.getTime()))
                C_e = self.compute_elem_capacity(e)
                A_e = K_e * self.Tau + C_e / dt
                P_e = np.subtract(C_e / dt, K_e * (1. - self.Tau))
                # #Assemble
                # print e, self.loc[c[e.number-1,0]],self.loc[c[e.number-1,1]], self.loc[c[e.number-1,2]], self.loc[c[e.number-1,3]]
                for i in range(ndofs):  # loop of dofs
                    ii = self.loc[c[e.number - 1, i]]  # code number
                    if ii < self.neq:  # unknown to be solved
                        for j in range(ndofs):
                            jj = self.loc[c[e.number - 1, j]]
                            if jj < self.neq:
                                self.kuu[ii, jj] += A_e[i, j]
                            else:
                                self.kup[ii, jj - self.neq] += A_e[i, j]
                    else:  # prescribed value
                        for j in range(ndofs):
                            jj = self.loc[c[e.number - 1, j]]
                            if jj >= self.neq:
                                self.kpp[ii - self.neq, jj - self.neq] += A_e[i, j]

                    # rhs mtrx P=C/dt - K*(1-Tau)
                    for j in range(ndofs):
                        jj = self.loc[c[e.number - 1, j]]
                        self.P[ii, jj] += P_e[i, j]

            # add boundary terms
            # print ('convection BC', self.convectionBC)
            # exit(0)
            for i in self.convectionBC:
                # print "Processing bc:", i
                elem = mesh.getCell(i[0])
                side = i[1]
                h = i[2]
                Te = i[3]
                # print ("h:%f Te:%f" % (h, Te))

                n1 = elem.getVertices()[side]
                n2 = elem.getVertices()[0 if side + 1 == elem.getNumberOfVertices() else side + 1]

                length = math.sqrt((n2.coords[0] - n1.coords[0]) * (n2.coords[0] - n1.coords[0]) +
                                   (n2.coords[1] - n1.coords[1]) * (n2.coords[1] - n1.coords[1]))

                # print (h, Te, length)

                # boundary_lhs=h*(np.dot(N.T,N))
                boundary_lhs = np.zeros((2, 2))
                if self.tria:
                    boundary_lhs[0, 0] = h * (1. / 4.) * length
                    boundary_lhs[0, 1] = h * (1. / 4.) * length
                    boundary_lhs[1, 0] = h * (1. / 4.) * length
                    boundary_lhs[1, 1] = h * (1. / 4.) * length
                else:
                    boundary_lhs[0, 0] = h * (1. / 3.) * length
                    boundary_lhs[0, 1] = h * (1. / 6.) * length
                    boundary_lhs[1, 0] = h * (1. / 6.) * length
                    boundary_lhs[1, 1] = h * (1. / 3.) * length

                # Assemble
                loci = [n1.number, n2.number]
                # print loci
                for i in range(2):  # loop nb of dofs
                    ii = self.loc[loci[i]]
                    if ii < self.neq:
                        for j in range(2):
                            jj = self.loc[loci[j]]
                            if jj < self.neq:
                                # print "Assembling bc ", ii, jj, boundary_lhs[i,j]
                                self.kuu[ii, jj] += boundary_lhs[i, j] * self.Tau

                    for j in range(2):
                        jj = self.loc[loci[j]]
                        self.P[ii, jj] += boundary_lhs[i, j] * self.Tau

            self.T = np.zeros(self.neq + self.pneq)  # vector of current prescribed temperatures
            self.b = np.zeros(self.neq)  # rhs vector

        # end self.init

        # update solution Tp = T
        # update rhs bp = b
        self.Tp = np.copy(self.T)
        self.bp = np.copy(self.b)

        # initialize prescribed Temperatures in current solution vector (T):
        for i in range(self.mesh.getNumberOfVertices()):
            if i in self.dirichletBCs:
                ii = self.loc[i]
                self.T[ii] = self.dirichletBCs[i]  # assign temperature

        # evaluate RHS
        # add boundary terms due to prescribed fluxes
        self.b = np.zeros(self.neq)
        for i in self.convectionBC:
            # print "Processing bc:", i
            elem = mesh.getCell(i[0])
            side = i[1]
            h = i[2]
            Te = i[3]
            # print ("h:%f Te:%f" % (h, Te))

            n1 = elem.getVertices()[side]
            # print n1
            n2 = elem.getVertices()[0 if side + 1 == elem.getNumberOfVertices() else side + 1]

            length = math.sqrt((n2.coords[0] - n1.coords[0]) * (n2.coords[0] - n1.coords[0]) +
                               (n2.coords[1] - n1.coords[1]) * (n2.coords[1] - n1.coords[1]))

            # print h, Te, length
            # boundary_rhs=h*Te*N.T
            boundary_rhs = np.zeros((2, 1))
            boundary_rhs[0] = h * (1. / 2.) * length * Te
            boundary_rhs[1] = h * (1. / 2.) * length * Te

            # #Assemble
            loci = [n1.number, n2.number]
            # print loci
            for i in range(2):  # loop nb of dofs
                ii = self.loc[loci[i]]
                if ii < self.neq:
                    self.b[ii] += boundary_rhs[i]

        rhs = self.b * self.Tau + self.bp * (1 - self.Tau)
        # add rhs due to previous state (C/dt-K(1-Tau))*r_{i-1}
        tmp = np.dot(self.P, self.Tp)  # contains all DOFs, extract unknown part and add it to rhs
        rhs = rhs + tmp[:self.neq]

        # add effect of dirichlet BCS
        rhs = np.subtract(rhs, np.dot(self.kup, self.T[self.neq:self.neq + self.pneq]))

        self.r = np.zeros(self.pneq)  # reactions
        # solve linear system
        log.info("Solving thermal nonstationary problem")
        self.T[:self.neq] = np.linalg.solve(self.kuu, rhs)  # inefficient, should reuse existing factorization !!!
        self.r = np.dot(self.kup.transpose(), self.T[:self.neq]) + np.dot(self.kpp,
                                                                          self.T[self.neq:self.neq + self.pneq])
        # print (self.r)

        log.info("Done")
        log.info("Time consumed %f s" % (timeTime.time() - start))


@Pyro4.expose
class mechanical(Application.Application):
    """ Simple mechanical solver on 2D rectanglar domain (plane stress problem) """

    def __init__(self, file="", workdir="."):
        super(mechanical, self).__init__(file, workdir)
        self.E = 30.0e+9  # ceramics
        self.nu = 0.25  # ceramics
        self.fx = [0., 0., 0., 0.]  # load in x
        self.fy = [0., 0., 0., 0.]  # load in y
        self.temperatureField = None
        self.alpha = 12.e-6
        self.thick = 1.0

        self.metadata.update({'name': 'mechanical', 'type': '',
                              'inputs': [
                                  {'name': 'temperature', 'obj_type': 'mupif.FieldID.FID_Temperature', 'type': 'Field',
                                   'optional': False}
                              ],
                              'outputs': [
                                  {'name': 'displacement', 'obj_type': 'mupif.FieldID.FID_Displacement', 'type': 'Field',
                                   'optional': True}
                              ]})

        if self.file != "":
            self.readInput()

    def getCriticalTimeStep(self):
        return PQ.PhysicalQuantity(0.4, 's')

    def getAssemblyTime(self, tstep):
        return tstep.getTime()

    def readInput(self):

        self.dirichletModelEdges = []
        self.loadModelEdges = []
        try:
            f = open(self.workDir + os.path.sep + self.file, 'r')
            # size
            line = getline(f)
            size = line.split()
            self.xl = float(size[0])
            self.yl = float(size[1])
            # mesh
            line = getline(f)
            ne = line.split()
            self.nx = int(ne[0])
            self.ny = int(ne[1])
            # Thickness
            rec = getline(f).split()
            self.thick = float(rec[0])
            # Young's modulus and Poissons' ratio
            rec = getline(f).split()
            self.E = float(rec[0])
            self.nu = float(rec[1])
            # thermal dilation
            rec = getline(f).split()
            self.alpha = float(rec[0])

            log.info("Mechanical problem's dimensions: (%g, %g)" % (self.xl, self.yl))

            for iedge in range(4):
                line = getline(f)
                rec = line.split()
                edge = int(rec[0])
                code = rec[1]
                if (code == 'D'):
                    self.dirichletModelEdges.append(edge)
                elif (code == 'C'):
                    self.loadModelEdges.append(edge)
                    self.fx[iedge] = float(rec[2])
                    self.fy[iedge] = float(rec[3])

            # print(self.fx, self.fy)
            f.close()

        except  Exception as e:
            log.exception(e)
            exit(1)

    def prepareTask(self):

        self.mesh = Mesh.UnstructuredMesh()
        # generate a simple mesh here
        # self.xl = 0.5 # domain (0..xl)(0..yl)
        # self.yl = 0.3
        # self.nx = 10 # number of elements in x direction
        # self.ny = 10 # number of elements in y direction
        self.dx = self.xl / self.nx
        self.dy = self.yl / self.ny
        self.mesh = meshgen.meshgen((0., 0.), (self.xl, self.yl), self.nx, self.ny)

        k = 1
        #
        # Model edges
        #     ----------3----------
        #     |                   |
        #     4                   2
        #     |                   |
        #     ----------1---------
        #

        # self.dirichletModelEdges=(3,4,1)#
        self.dirichletBCs = {}  # key is node number, value is prescribed temperature (zero supported only now)
        for ide in self.dirichletModelEdges:
            if ide == 1:
                for i in range(self.nx + 1):
                    self.dirichletBCs[i * (self.ny + 1)] = (0.0, 0.0, 0.0)
            elif ide == 2:
                for i in range(self.ny + 1):
                    self.dirichletBCs[self.nx * (self.ny + 1) + i] = (0.0, 0.0, 0.0)
            elif ide == 3:
                for i in range(self.nx + 1):
                    self.dirichletBCs[self.ny + i * (self.ny + 1)] = (0.0, 0.0, 0.0)
            elif ide == 4:
                for i in range(self.ny + 1):
                    self.dirichletBCs[i] = (0.0, 0.0, 0.0)

        # convectionModelEdges=(2,)
        self.loadBC = []
        for ice in self.loadModelEdges:
            if ice == 1:
                for i in range(self.nx):
                    self.loadBC.append((self.ny * i, 0, self.fx[ice - 1], self.fy[ice - 1]))
            elif ice == 2:
                for i in range(self.ny):
                    self.loadBC.append(((self.nx - 1) * self.ny + i, 1, self.fx[ice - 1], self.fy[ice - 1]))
            elif ice == 3:
                for i in range(self.nx):
                    self.loadBC.append((self.ny * (i + 1) - 1, 2, self.fx[ice - 1], self.fy[ice - 1]))
            elif ice == 4:
                for i in range(self.ny):
                    self.loadBC.append((i, 3, self.fx[ice - 1], self.fy[ice - 1]))

        self.loc = np.zeros((self.mesh.getNumberOfVertices(), 2), dtype=np.int32)  # Du, Dv dofs per node
        for i in self.dirichletBCs:
            self.loc[i, 0] = -1
            self.loc[i, 1] = -1
        self.neq = 0
        for i in range(self.mesh.getNumberOfVertices()):
            for j in range(2):  # loop over nodal DOFs
                if (self.loc[i, j] >= 0):
                    self.loc[i, j] = self.neq
                    self.neq = self.neq + 1

        # print "loc:", self.loc

    def getField(self, fieldID, time, objectID=0):
        if fieldID == FieldID.FID_Displacement:
            values = []
            for i in range(self.mesh.getNumberOfVertices()):
                if time.getValue() == 0.0:  # put zeros everywhere
                    values.append((0., 0., 0.))
                else:
                    if i in self.dirichletBCs:
                        values.append(self.dirichletBCs[i])
                    else:
                        values.append((self.T[self.loc[i, 0], 0], self.T[self.loc[i, 1], 0], 0.0))

            return Field.Field(self.mesh, FieldID.FID_Displacement, ValueType.ValueType.Vector, 'm', time, values)
        else:
            raise APIError.APIError('Unknown field ID')

    def setField(self, field, fieldID=0):
        if field.getFieldID() == FieldID.FID_Temperature:
            self.temperatureField = field

    def solveStep(self, tstep, stageID=0, runInBackground=False):
        # self.readInput()
        self.prepareTask()
        mesh = self.mesh
        if tstep and tstep.getNumber() == 0:  # assign mesh only for 0th time step
            return
        rule = IntegrationRule.GaussIntegrationRule()
        self.volume = 0.0
        self.integral = 0.0

        numNodes = mesh.getNumberOfVertices()
        numElements = mesh.getNumberOfCells()
        elemNodes = 4
        nodalDofs = 2
        elemDofs = elemNodes * nodalDofs

        # print numNodes
        # print numElements
        # print ndofs

        start = timeTime.time()
        log.info(self.getApplicationSignature())
        log.info("Number of equations: %d" % self.neq)

        # connectivity
        c = np.zeros((numElements, elemNodes), dtype=np.int32)
        for e in range(0, numElements):
            for i in range(0, elemNodes):
                c[e, i] = self.mesh.getVertex(mesh.getCell(e).vertices[i]).label
        # print "connectivity :",c

        # Global matrix and global vector
        A = np.zeros((self.neq, self.neq))
        b = np.zeros((self.neq, 1))

        log.info("Assembling ...")
        for e in mesh.cells():
            # element matrix and element vector
            A_e = np.zeros((elemDofs, elemDofs))
            b_e = np.zeros((elemDofs, 1))

            ngp = rule.getRequiredNumberOfPoints(e.getGeometryType(), 2)
            pnts = rule.getIntegrationPoints(e.getGeometryType(), ngp)

            # print "e : ",e.number-1
            # print "ngp :",ngp
            # print "pnts :",pnts

            for p in pnts:  # loop over ips
                detJ = e.getTransformationJacobian(p[0])
                # print "Jacobian: ",detJ

                dv = detJ * p[1]
                # print "dv :",dv

                N = np.zeros((1, elemNodes))
                tmp = e._evalN(p[0])
                N = np.asarray(tmp)
                # print "N :",N

                x = e.loc2glob(p[0])
                # print "global coords :", x

                k = 1.
                Grad = np.zeros((3, elemDofs))
                Grad = self.compute_B(e, p[0])
                D = self.compute_D(self.E, self.nu)
                # print "Grad :",Grad
                K = np.zeros((elemDofs, elemDofs))
                K = k * (np.dot(Grad.T, np.dot(D, Grad)))

                # Stiffness matrix
                for i in range(elemDofs):  # loop dofs
                    for j in range(elemDofs):
                        A_e[i, j] += K[i, j] * dv

                        # temperature load if temperature field registered
                if self.temperatureField:
                    t = self.temperatureField.evaluate(x)
                    et = np.zeros((3, 1))
                    et[0] = self.alpha * t.getValue()[0]
                    et[1] = self.alpha * t.getValue()[0]
                    et[2] = 0.0
                    b_e = np.dot(Grad.T, np.dot(D, et)) * dv
            # print "A_e :",A_e
            # print "b_e :",b_e

            # #Assemble
            # print e, self.loc[c[e.number-1,0]],self.loc[c[e.number-1,1]], self.loc[c[e.number-1,2]], self.loc[c[e.number-1,3]]
            for i in range(elemNodes):  # loop nb of dofs
                for id in range(nodalDofs):
                    ii = int(self.loc[c[e.number - 1, i], id])
                    if (ii >= 0):
                        for j in range(elemNodes):
                            for jd in range(nodalDofs):
                                jj = int(self.loc[c[e.number - 1, j], jd])
                                if (jj >= 0):
                                    # print "Assembling", ii, jj
                                    A[ii, jj] += A_e[i * nodalDofs + id, j * nodalDofs + jd]
                        b[ii] += b_e[i * nodalDofs + id]

                        # print A
        # print b

        # add boundary terms
        for i in self.loadBC:
            # print "Processing bc:", i
            elem = mesh.getCell(i[0])
            side = i[1]
            fx = i[2]  # specified as intensity per edge length [N/m]
            fy = i[3]  # specified as intensity per edge length [N/m]
            # print(fx,fy)

            n1 = elem.getVertices()[side]
            # print n1
            if (side == 3):
                n2 = elem.getVertices()[0]
            else:
                n2 = elem.getVertices()[side + 1]

            length = math.sqrt((n2.coords[0] - n1.coords[0]) * (n2.coords[0] - n1.coords[0]) +
                               (n2.coords[1] - n1.coords[1]) * (n2.coords[1] - n1.coords[1]))

            # boundary_rhs=h*Te*N.T
            boundary_rhs = np.zeros((2, 2))
            boundary_rhs[0, 0] = (1. / 2.) * length * fx
            boundary_rhs[1, 0] = (1. / 2.) * length * fx
            boundary_rhs[0, 1] = (1. / 2.) * length * fy
            boundary_rhs[1, 1] = (1. / 2.) * length * fy

            # #Assemble
            loci = [n1.number, n2.number]
            # print loci
            for i in range(2):  # loop nb of nodes
                for id in range(2):  # loop over dofs
                    ii = self.loc[loci[i], id]
                    if ii >= 0:
                        b[ii] += boundary_rhs[i, id]

                        # print A
        # print b

        # solve linear system
        log.info("Solving mechanical problem")
        self.T = np.linalg.solve(A, b)
        log.info("Done")
        log.info("Time consumed %f s" % (timeTime.time() - start))

    def compute_B(self, elem, lc):
        vertices = elem.getVertices()
        c1 = vertices[0].coords
        c2 = vertices[1].coords
        c3 = vertices[2].coords
        c4 = vertices[3].coords

        B11 = 0.25 * (c1[0] - c2[0] - c3[0] + c4[0])
        B12 = 0.25 * (c1[0] + c2[0] - c3[0] - c4[0])
        B21 = 0.25 * (c1[1] - c2[1] - c3[1] + c4[1])
        B22 = 0.25 * (c1[1] + c2[1] - c3[1] - c4[1])

        C11 = 0.25 * (c1[0] - c2[0] + c3[0] - c4[0])
        C12 = 0.25 * (c1[0] - c2[0] + c3[0] - c4[0])
        C21 = 0.25 * (c1[1] - c2[1] + c3[1] - c4[1])
        C22 = 0.25 * (c1[1] - c2[1] + c3[1] - c4[1])

        # local coords
        ksi = lc[0]
        eta = lc[1]

        B = np.zeros((2, 2))
        B[0, 0] = (1. / elem.getTransformationJacobian(lc)) * (B22 + ksi * C22)
        B[0, 1] = (1. / elem.getTransformationJacobian(lc)) * (-B21 - eta * C21)
        B[1, 0] = (1. / elem.getTransformationJacobian(lc)) * (-B12 - ksi * C12)
        B[1, 1] = (1. / elem.getTransformationJacobian(lc)) * (B11 + eta * C11)

        dNdksi = np.zeros((2, 4))
        dNdksi[0, 0] = 0.25 * (1. + eta)
        dNdksi[0, 1] = -0.25 * (1. + eta)
        dNdksi[0, 2] = -0.25 * (1. - eta)
        dNdksi[0, 3] = 0.25 * (1. - eta)
        dNdksi[1, 0] = 0.25 * (1. + ksi)
        dNdksi[1, 1] = 0.25 * (1. - ksi)
        dNdksi[1, 2] = -0.25 * (1. - ksi)
        dNdksi[1, 3] = -0.25 * (1. + ksi)

        Grad = np.zeros((2, 4))
        Grad = np.dot(B, dNdksi)

        B = np.zeros((3, 8))
        B[0, 0] = Grad[0, 0]
        B[0, 2] = Grad[0, 1]
        B[0, 4] = Grad[0, 2]
        B[0, 6] = Grad[0, 3]

        B[1, 1] = Grad[1, 0]
        B[1, 3] = Grad[1, 1]
        B[1, 5] = Grad[1, 2]
        B[1, 7] = Grad[1, 3]

        B[2, 0] = Grad[1, 0]
        B[2, 1] = Grad[0, 0]
        B[2, 2] = Grad[1, 1]
        B[2, 3] = Grad[0, 1]
        B[2, 4] = Grad[1, 2]
        B[2, 5] = Grad[0, 2]
        B[2, 6] = Grad[1, 3]
        B[2, 7] = Grad[0, 3]

        return B

    def compute_D(self, E, nu):
        D = np.zeros((3, 3))
        ee = E / (1. - nu * nu)
        G = E / (2.0 * (1. + nu))

        D[0, 0] = ee
        D[0, 1] = nu * ee
        D[1, 0] = nu * ee
        D[1, 1] = ee
        D[2, 2] = G
        D = D * self.thick
        return D

    def getApplicationSignature(self):
        return "Mechanical-demo-solver, ver 1.0"


# @Pyro4.expose
# class EulerBernoulli(Application.Application):
#     """Calculates maximum deflection of cantilever beam with a uniform vertical distributed load. Uses Euler-Bernoulli beam neglecting shear deformation."""
#
#     def __init__(self, b, h, L, E, f):
#         self.b = b
#         self.h = h
#         self.L = L
#         self.E = E
#         self.f = f
#         self.deflection = 0.
#
#     def solveStep(self, tstep, stageID=0, runInBackground=False):
#         I = self.b * self.h ** 3 / 12.
#         self.deflection = self.f * self.L ** 4 / 8. / self.E / I
#
#     def getField(self, fieldID, time, objectID=0):
#         if fieldID == FieldID.FID_Displacement:
#             return self.deflection