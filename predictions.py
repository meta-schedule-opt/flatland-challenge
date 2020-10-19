from collections import namedtuple

import numpy as np

from flatland.core.env_prediction_builder import PredictionBuilder
from flatland.envs.rail_env import RailAgentStatus
from flatland.utils.ordered_set import OrderedSet


Prediction = namedtuple('Prediction', ['lenght', 'path', 'edges', 'positions'])


def _empty_prediction():
    '''
    Return an empty Prediction namedtuple
    '''
    return Prediction(
        lenght=np.inf, path=[], edges=[], positions=[]
    )


class ShortestPathPredictor(PredictionBuilder):

    def __init__(self, max_depth=None):
        super().__init__(max_depth)

    def reset(self):
        '''
        Initialize shortest paths for each agent
        '''
        self._shortest_paths = dict()
        for agent in self.env.agents:
            self._shortest_paths[agent.handle] = self.railway_encoding.shortest_paths(
                agent.handle
            )

    def get_shortest_path(self, handle):
        '''
        Keep a list of shortest paths for the given agent.
        At each time step, update the already compute paths and delete the ones
        which cannot be followed anymore.
        The returned shortest paths have the agent's position as the first element.
        '''
        position = self.railway_encoding.get_agent_cell(handle)
        node, _ = self.railway_encoding.next_node(position)
        chosen_path = None
        paths_to_delete = []
        for i, shortest_path in enumerate(self._shortest_paths[handle]):
            lenght, path = shortest_path
            # Delete divergent path
            if node != path[0] and node != path[1]:
                paths_to_delete = [i] + paths_to_delete
                continue

            # Update agent position
            if path[0] != position:
                lenght -= 1
            path[0] = position

            # If the agent is on a packed graph node, drop it
            if path[0] == path[1]:
                path = path[1:]

            # Agent arrived to target
            if lenght == 0:
                chosen_path = lenght, path
                break

            # Select this path if no other path has been previously selected
            if chosen_path is None:
                chosen_path = lenght, path

            # Update shortest path
            self._shortest_paths[handle][i] = lenght, path

        # Delete divergent paths
        for i in paths_to_delete:
            del self._shortest_paths[handle][i]

        # Compute shortest paths, if no path is already available
        if chosen_path is None:
            self._shortest_paths[handle] = self.railway_encoding.shortest_paths(
                handle
            )
            if not self._shortest_paths[handle]:
                return np.inf, []

            chosen_path = self._shortest_paths[handle][0]

        return chosen_path

    def get_deviation_paths(self, handle, path):
        '''
        Return one deviation path for at most `max_depth` nodes in the given path
        and limit the computed path lenghts by `max_depth`
        '''
        start = 0
        depth = min(self.max_depth or len(path), len(path))
        deviation_paths = dict()
        source, _ = self.railway_encoding.next_node(path[0])
        if source != path[0]:
            start = 1
            deviation_paths = {path[0]: []}
        for i in range(start, depth - 1):
            paths = self.railway_encoding.deviation_paths(
                handle, path[i], path[i + 1]
            )
            deviation_path = []
            lenght = 0
            if paths:
                deviation_path = paths[0][1]
                lenght = paths[0][0]
                edges = self.railway_encoding.edges_from_path(
                    deviation_path[:self.max_depth]
                )
                pos = self.railway_encoding.positions_from_path(
                    deviation_path[:self.max_depth]
                )
                deviation_paths[path[i]] = Prediction(
                    lenght=lenght,
                    path=deviation_path[:self.max_depth],
                    edges=edges,
                    positions=pos
                )
            else:
                deviation_paths[path[i]] = _empty_prediction()

        return deviation_paths

    def get_many(self):
        '''
        Build the prediction for every agent
        '''
        prediction_dict = {}
        for agent in self.env.agents:
            prediction_dict[agent.handle] = None
            if agent.malfunction_data["malfunction"] == 0:
                prediction_dict[agent.handle] = self.get(agent.handle)
        return prediction_dict

    def get(self, handle):
        '''
        Build the prediction for the given agent
        '''
        agent = self.env.agents[handle]
        if agent.status == RailAgentStatus.DONE_REMOVED or agent.status == RailAgentStatus.DONE:
            return None

        # Build predictions
        lenght, path = self.get_shortest_path(handle)
        if lenght < np.inf:
            edges = self.railway_encoding.edges_from_path(
                path[:self.max_depth]
            )
            pos = self.railway_encoding.positions_from_path(
                path[:self.max_depth]
            )
            shortest_path_prediction = Prediction(
                lenght=lenght, path=path[:self.max_depth], edges=edges, positions=pos
            )
            deviation_paths_prediction = self.get_deviation_paths(handle, path)
        else:
            shortest_path_prediction = _empty_prediction()
            deviation_paths_prediction = dict()

        # Update GUI
        visited = OrderedSet()
        visited.update(shortest_path_prediction.positions)
        self.env.dev_pred_dict[handle] = visited

        return (shortest_path_prediction, deviation_paths_prediction)

    def set_env(self, env):
        super().set_env(env)

    def set_railway_encoding(self, railway_encoding):
        self.railway_encoding = railway_encoding
